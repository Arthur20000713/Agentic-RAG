"""Repeatable HTTP benchmark for the Java business and AI integration paths."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import statistics
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Sample:
    elapsed_ms: float
    status: int
    error: str | None = None


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(samples: list[Sample], duration_seconds: float) -> dict[str, Any]:
    latencies = [sample.elapsed_ms for sample in samples]
    errors = [sample for sample in samples if sample.error is not None or sample.status >= 400]
    total = len(samples)
    return {
        "requests": total,
        "errors": len(errors),
        "errorRate": len(errors) / total if total else 1.0,
        "throughputRps": total / duration_seconds if duration_seconds > 0 else 0.0,
        "latencyMs": {
            "min": min(latencies, default=0.0),
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies, default=0.0),
        },
        "statusCounts": {
            str(status): sum(1 for sample in samples if sample.status == status)
            for status in sorted({sample.status for sample in samples})
        },
        "errorCounts": {
            error: sum(1 for sample in errors if sample.error == error)
            for error in sorted({sample.error for sample in errors if sample.error})
        },
    }


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Sample, dict[str, Any] | None]:
        request_headers = {"Accept": "application/json"}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=request_headers,
            method=method,
        )
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = response.status
            payload = json.loads(raw.decode("utf-8")) if raw else None
            return Sample((time.perf_counter() - started) * 1000, status), payload
        except HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            error_code = "http"
            if isinstance(payload, dict):
                candidate = payload.get("error", {}).get("code")
                if isinstance(candidate, str) and candidate:
                    error_code = candidate
            return Sample((time.perf_counter() - started) * 1000, exc.code, error_code), payload
        except (TimeoutError, URLError, OSError) as exc:
            return Sample((time.perf_counter() - started) * 1000, 0, type(exc).__name__), None


def login(client: ApiClient, username: str, password: str) -> str:
    sample, payload = client.request(
        "POST",
        "/api/v1/auth/login",
        body={"username": username, "password": password},
        headers={"X-Request-ID": f"req-p7-benchmark-login-{uuid.uuid4().hex}"},
    )
    if sample.status != 200 or not payload:
        raise RuntimeError(f"Login failed with HTTP {sample.status}")
    token = payload.get("data", {}).get("accessToken")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Login response did not contain an access token")
    return token


def create_conversation(client: ApiClient, token: str, run_id: str, worker: int) -> dict[str, Any]:
    sample, payload = client.request(
        "POST",
        "/api/v1/conversations",
        token=token,
        body={"title": f"P7 benchmark {run_id} worker {worker}"},
        headers={"X-Request-ID": f"req-p7-setup-{run_id}-{worker}"},
    )
    if sample.status != 201 or not payload:
        raise RuntimeError(f"Conversation setup failed with HTTP {sample.status}")
    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Conversation setup returned an invalid payload")
    return data


def cleanup_conversation(client: ApiClient, token: str, conversation_id: str) -> None:
    sample, payload = client.request("GET", f"/api/v1/conversations/{conversation_id}", token=token)
    if sample.status != 200 or not payload:
        return
    version = payload.get("data", {}).get("conversation", {}).get("version")
    if version is None:
        version = payload.get("data", {}).get("version")
    if version is None:
        return
    query = urlencode({"version": version})
    client.request("DELETE", f"/api/v1/conversations/{conversation_id}?{query}", token=token)


def run_business_worker(
    client: ApiClient,
    token: str,
    deadline: float,
    interval_seconds: float,
) -> list[Sample]:
    samples: list[Sample] = []
    while time.monotonic() < deadline:
        started = time.monotonic()
        sample, _ = client.request(
            "GET",
            "/api/v1/conversations?scope=own&page=0&size=20",
            token=token,
        )
        samples.append(sample)
        remaining = interval_seconds - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(min(remaining, max(0.0, deadline - time.monotonic())))
    return samples


def run_ai_worker(
    client: ApiClient,
    token: str,
    conversation: dict[str, Any],
    worker: int,
    run_id: str,
    deadline: float,
    interval_seconds: float,
) -> list[Sample]:
    samples: list[Sample] = []
    context_version = int(conversation.get("contextVersion", 0))
    iteration = 0
    while time.monotonic() < deadline:
        started = time.monotonic()
        idempotency_key = f"p7-bench-{run_id}-{worker}-{iteration}"
        sample, _ = client.request(
            "POST",
            f"/api/v1/conversations/{conversation['id']}/messages",
            token=token,
            body={
                "content": "一头育肥猪精神不振且采食量下降，请给出分诊建议。",
                "contextVersion": context_version,
            },
            headers={
                "Idempotency-Key": idempotency_key,
                "X-Request-ID": f"req-{idempotency_key}",
            },
        )
        samples.append(sample)
        if sample.status in (200, 202):
            context_version += 1
        iteration += 1
        remaining = interval_seconds - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(min(remaining, max(0.0, deadline - time.monotonic())))
    return samples


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("business-stub", "ai-stub", "ai-real"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--username", default=os.getenv("BOOTSTRAP_ADMIN_USERNAME"))
    parser.add_argument("--password", default=os.getenv("BOOTSTRAP_ADMIN_PASSWORD"))
    parser.add_argument("--duration-seconds", type=positive_float, default=300.0)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--interval-seconds", type=positive_float, default=1.0)
    parser.add_argument("--timeout-seconds", type=positive_float, default=20.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=positive_float)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-real-ai", action="store_true")
    parser.add_argument("--rag-mode-evidence")
    parser.add_argument("--model")
    parser.add_argument("--knowledge-base")
    parser.add_argument("--knowledge-base-size")
    parser.add_argument("--keep-conversations", action="store_true")
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("--username and --password (or bootstrap admin environment variables) are required")
    if args.concurrency is None:
        args.concurrency = {
            "business-stub": 50,
            "ai-stub": 20,
            "ai-real": 5,
        }[args.profile]
    if args.concurrency <= 0:
        parser.error("--concurrency must be greater than zero")
    if not 0 <= args.max_error_rate <= 1:
        parser.error("--max-error-rate must be between 0 and 1")
    if args.profile == "ai-real" and (
        not args.confirm_real_ai
        or not args.rag_mode_evidence
        or not args.model
        or not args.knowledge_base
        or not args.knowledge_base_size
    ):
        parser.error(
            "ai-real requires --confirm-real-ai, --rag-mode-evidence, --model, "
            "--knowledge-base, and --knowledge-base-size"
        )

    max_p95_ms = args.max_p95_ms or (300.0 if args.profile == "business-stub" else 5000.0)
    client = ApiClient(args.base_url, args.timeout_seconds)
    token = login(client, args.username, args.password)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    conversations: list[dict[str, Any]] = []
    samples: list[Sample] = []
    wall_started = time.perf_counter()
    workload_elapsed = 0.0
    try:
        if args.profile != "business-stub":
            conversations = [
                create_conversation(client, token, run_id, worker)
                for worker in range(args.concurrency)
            ]
        workload_started = time.perf_counter()
        deadline = time.monotonic() + args.duration_seconds
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            if args.profile == "business-stub":
                futures = [
                    executor.submit(
                        run_business_worker,
                        client,
                        token,
                        deadline,
                        args.interval_seconds,
                    )
                    for _ in range(args.concurrency)
                ]
            else:
                futures = [
                    executor.submit(
                        run_ai_worker,
                        client,
                        token,
                        conversation,
                        worker,
                        run_id,
                        deadline,
                        args.interval_seconds,
                    )
                    for worker, conversation in enumerate(conversations)
                ]
            for future in concurrent.futures.as_completed(futures):
                samples.extend(future.result())
        workload_elapsed = time.perf_counter() - workload_started
    finally:
        if conversations and not args.keep_conversations:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(conversations))) as executor:
                list(
                    executor.map(
                        lambda conversation: cleanup_conversation(
                            client, token, str(conversation["id"])
                        ),
                        conversations,
                    )
                )

    total_wall_duration = time.perf_counter() - wall_started
    metrics = summarize(samples, workload_elapsed)
    passed = (
        metrics["requests"] > 0
        and metrics["errorRate"] <= args.max_error_rate
        and metrics["latencyMs"]["p95"] <= max_p95_ms
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "runId": run_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "ragMode": "real" if args.profile == "ai-real" else "stub",
        "ragModeEvidence": args.rag_mode_evidence if args.profile == "ai-real" else "compose RAG_QUERY_MODE=fake",
        "model": args.model if args.profile == "ai-real" else "deterministic fake RAG",
        "knowledgeBase": args.knowledge_base if args.profile == "ai-real" else "compose test fixture",
        "knowledgeBaseSize": args.knowledge_base_size if args.profile == "ai-real" else "fixture-only",
        "target": args.base_url,
        "workload": {
            "concurrency": args.concurrency,
            "requestedDurationSeconds": args.duration_seconds,
            "workloadDurationSeconds": workload_elapsed,
            "totalWallDurationSeconds": total_wall_duration,
            "intervalSeconds": args.interval_seconds,
            "timeoutSeconds": args.timeout_seconds,
        },
        "thresholds": {"maxErrorRate": args.max_error_rate, "maxP95Ms": max_p95_ms},
        "metrics": metrics,
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "logicalCpuCount": os.cpu_count(),
            "python": platform.python_version(),
        },
        "samplesRedacted": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
