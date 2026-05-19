from __future__ import annotations

import asyncio
import inspect
import json
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.app.model.local_schema import parse_local_json_response


LocalTransport = Callable[[str, dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class LocalBackendRequest:
    prompt: str
    schema_name: str
    endpoint: str
    model: str
    timeout_seconds: float = 3.0
    context: dict[str, Any] | None = None
    options: dict[str, Any] = field(default_factory=dict)


TransformersGenerator = Callable[[str, LocalBackendRequest], str]


@dataclass(frozen=True)
class LocalBackendResponse:
    status: str
    schema_name: str
    content: dict[str, Any]
    fallback_required: bool
    provider: str
    latency_ms: int
    raw_text: str | None = None
    error_code: str | None = None
    reason: str | None = None
    request_payload: dict[str, Any] | None = None


class BaseLocalBackend(ABC):
    provider: str

    @abstractmethod
    async def generate(self, request: LocalBackendRequest) -> LocalBackendResponse:
        """Generate structured local-model output or a structured fallback result."""


class OllamaBackend(BaseLocalBackend):
    provider = "ollama"

    def __init__(self, transport: LocalTransport | None = None) -> None:
        self._transport = transport or _post_json

    async def generate(self, request: LocalBackendRequest) -> LocalBackendResponse:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": False,
            "format": "json",
        }
        if request.options:
            payload["options"] = request.options

        url = _ollama_generate_url(request.endpoint)
        try:
            raw = self._transport(url, payload, request.timeout_seconds)
            if inspect.isawaitable(raw):
                raw = await raw
        except TimeoutError as exc:
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_TIMEOUT",
                reason=str(exc) or "local model request timed out",
            )
        except Exception as exc:
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_HTTP_ERROR",
                reason=str(exc) or exc.__class__.__name__,
            )

        if not isinstance(raw, dict):
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_HTTP_ERROR",
                reason="local model response must be a JSON object",
            )
        if raw.get("error"):
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_HTTP_ERROR",
                reason=str(raw["error"]),
            )

        raw_text = _extract_ollama_text(raw)
        content = parse_local_json_response(raw_text, request.schema_name)
        return LocalBackendResponse(
            status=str(content.get("status", "success")),
            schema_name=request.schema_name.strip().lower(),
            content=content,
            fallback_required=bool(content.get("fallback_required")),
            provider=self.provider,
            latency_ms=_latency_ms(started),
            raw_text=raw_text,
            error_code=content.get("error_code"),
            reason=content.get("reason"),
            request_payload=payload,
        )

    def _failure(
        self,
        request: LocalBackendRequest,
        payload: dict[str, Any],
        started: float,
        *,
        error_code: str,
        reason: str,
    ) -> LocalBackendResponse:
        content = {
            "status": "error",
            "schema_name": request.schema_name.strip().lower(),
            "fallback_required": True,
            "error_code": error_code,
            "reason": reason,
        }
        return LocalBackendResponse(
            status="error",
            schema_name=request.schema_name.strip().lower(),
            content=content,
            fallback_required=True,
            provider=self.provider,
            latency_ms=_latency_ms(started),
            error_code=error_code,
            reason=reason,
            request_payload=payload,
        )


class TransformersBackend(BaseLocalBackend):
    provider = "transformers"

    def __init__(self, generator: TransformersGenerator | None = None) -> None:
        self._generator = generator
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._loaded_model_name: str | None = None

    async def generate(self, request: LocalBackendRequest) -> LocalBackendResponse:
        started = time.perf_counter()
        payload = {
            "model": request.model,
            "schema_name": request.schema_name,
            "device": request.options.get("device", "auto"),
            "torch_dtype": request.options.get("torch_dtype", "auto"),
            "max_new_tokens": request.options.get("max_new_tokens", 128),
            "temperature": request.options.get("temperature", 0.0),
        }
        normalized_schema = request.schema_name.strip().lower()
        if normalized_schema != "query_normalization":
            return _backend_failure(
                request,
                self.provider,
                payload,
                started,
                error_code="LOCAL_MODEL_SCHEMA_UNSUPPORTED",
                reason="transformers backend currently supports query_normalization only",
            )

        prompt = _query_normalization_prompt(request.prompt)
        try:
            raw_text = await asyncio.wait_for(
                asyncio.to_thread(self._generate_text, prompt, request),
                timeout=request.timeout_seconds,
            )
        except TimeoutError as exc:
            return _backend_failure(
                request,
                self.provider,
                payload,
                started,
                error_code="LOCAL_MODEL_TIMEOUT",
                reason=str(exc) or "local transformers generation timed out",
            )
        except Exception as exc:
            error_code = (
                "LOCAL_MODEL_IMPORT_ERROR"
                if exc.__class__.__name__ == "ImportError"
                else "LOCAL_MODEL_GENERATION_ERROR"
            )
            return _backend_failure(
                request,
                self.provider,
                payload,
                started,
                error_code=error_code,
                reason=str(exc) or exc.__class__.__name__,
            )

        content = parse_local_json_response(raw_text, normalized_schema)
        content = _normalize_query_normalization_content(content, normalized_schema)
        return LocalBackendResponse(
            status=str(content.get("status", "success")),
            schema_name=normalized_schema,
            content=content,
            fallback_required=bool(content.get("fallback_required")),
            provider=self.provider,
            latency_ms=_latency_ms(started),
            raw_text=raw_text,
            error_code=content.get("error_code"),
            reason=content.get("reason"),
            request_payload=payload,
        )

    def _generate_text(self, prompt: str, request: LocalBackendRequest) -> str:
        if self._generator is not None:
            return self._generator(prompt, request)

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ImportError("install local transformers dependencies with: pip install -e .[transformers]") from exc

        if self._model is None or self._tokenizer is None or self._loaded_model_name != request.model:
            dtype = request.options.get("torch_dtype", "auto")
            model_kwargs: dict[str, Any] = {"trust_remote_code": False}
            if dtype:
                model_kwargs["torch_dtype"] = dtype
            device = str(request.options.get("device", "auto"))
            if device == "auto" and torch.cuda.is_available():
                model_kwargs["device_map"] = "auto"

            self._tokenizer = AutoTokenizer.from_pretrained(request.model, trust_remote_code=False)
            self._model = AutoModelForCausalLM.from_pretrained(request.model, **model_kwargs)
            if device not in {"auto", "cuda:0"} and hasattr(self._model, "to"):
                self._model.to(device)
            elif device == "cuda:0" and torch.cuda.is_available() and hasattr(self._model, "to") and "device_map" not in model_kwargs:
                self._model.to("cuda:0")
            self._loaded_model_name = request.model

        tokenizer = self._tokenizer
        model = self._model
        messages = [
            {
                "role": "system",
                "content": (
                    "You normalize livestock questions for retrieval. "
                    "Return exactly one JSON object and no prose. "
                    "Set fallback_required to false when you can produce a normalized query."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        if hasattr(tokenizer, "apply_chat_template"):
            input_ids = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
            )
            model_device = getattr(model, "device", None)
            if model_device is not None and hasattr(input_ids, "to"):
                input_ids = input_ids.to(model_device)
            attention_mask = None
        else:
            encoded = tokenizer(prompt, return_tensors="pt")
            input_ids = encoded["input_ids"]
            attention_mask = encoded.get("attention_mask")
            model_device = getattr(model, "device", None)
            if model_device is not None:
                input_ids = input_ids.to(model_device)
                if attention_mask is not None and hasattr(attention_mask, "to"):
                    attention_mask = attention_mask.to(model_device)

        temperature = float(request.options.get("temperature", 0.0))
        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": int(request.options.get("max_new_tokens", 128)),
            "do_sample": temperature > 0,
        }
        if attention_mask is not None:
            generate_kwargs["attention_mask"] = attention_mask
        if temperature > 0:
            generate_kwargs["temperature"] = temperature
        output_ids = model.generate(input_ids, **generate_kwargs)
        generated_ids = output_ids[0][len(input_ids[0]) :]
        return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def _ollama_generate_url(endpoint: str) -> str:
    return endpoint.rstrip("/") + "/api/generate"


def _extract_ollama_text(raw: dict[str, Any]) -> str:
    response = raw.get("response")
    if isinstance(response, str):
        return response
    message = raw.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return ""


def _latency_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("local model HTTP response must be a JSON object")
    return parsed


def _query_normalization_prompt(query: str) -> str:
    return (
        "Normalize the livestock user question for retrieval. Preserve the user's language and factual meaning. "
        "Remove filler words, keep animal species, symptoms, measurements, management topic, and constraints. "
        "Return exactly one JSON object with keys: status, normalized_query, language, fallback_required. "
        'Use status="success" and fallback_required=false when the question can be normalized. '
        "Use fallback_required=true only when the input is empty, unsafe, or not a livestock question. "
        'Example: {"status":"success","normalized_query":"calf weaning feed","language":"en","fallback_required":false}\n'
        f"User question: {query.strip()}"
    )


def _normalize_query_normalization_content(content: dict[str, Any], schema_name: str) -> dict[str, Any]:
    if schema_name != "query_normalization":
        return content
    if content.get("status") == "success" and str(content.get("normalized_query", "")).strip():
        content["fallback_required"] = False
    return content


def _backend_failure(
    request: LocalBackendRequest,
    provider: str,
    payload: dict[str, Any],
    started: float,
    *,
    error_code: str,
    reason: str,
) -> LocalBackendResponse:
    content = {
        "status": "error",
        "schema_name": request.schema_name.strip().lower(),
        "fallback_required": True,
        "error_code": error_code,
        "reason": reason,
    }
    return LocalBackendResponse(
        status="error",
        schema_name=request.schema_name.strip().lower(),
        content=content,
        fallback_required=True,
        provider=provider,
        latency_ms=_latency_ms(started),
        error_code=error_code,
        reason=reason,
        request_payload=payload,
    )
