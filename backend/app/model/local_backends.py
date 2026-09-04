from __future__ import annotations

import asyncio
import inspect
import json
import time
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.app.model.local_schema import parse_local_json_response
from backend.app.model.usage import ollama_usage, tokenizer_usage, unavailable_usage
from backend.app.schemas.model_routing import ModelTokenUsage

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
class LocalGeneration:
    text: str
    usage: ModelTokenUsage = field(default_factory=unavailable_usage)


@dataclass(frozen=True)
class LocalBackendResponse:
    status: str
    schema_name: str
    content: dict[str, Any]
    fallback_required: bool
    provider: str
    latency_ms: int
    usage: ModelTokenUsage = field(default_factory=unavailable_usage)
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
        normalized_schema = request.schema_name.strip().lower()
        structured_schemas = {"query_normalization", "intent_routing", "livestock_triage"}
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": (
                _prompt_for_schema(request.prompt, normalized_schema)
                if normalized_schema in structured_schemas
                else request.prompt
            ),
            "stream": False,
            "format": "json",
        }
        if normalized_schema in structured_schemas:
            payload["system"] = _system_prompt_for_schema(normalized_schema)
        ollama_options = _ollama_options(request.options)
        if ollama_options:
            payload["options"] = ollama_options

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
        content = _normalize_schema_content(content, normalized_schema)
        return LocalBackendResponse(
            status=str(content.get("status", "success")),
            schema_name=request.schema_name.strip().lower(),
            content=content,
            fallback_required=bool(content.get("fallback_required")),
            provider=self.provider,
            latency_ms=_latency_ms(started),
            usage=ollama_usage(raw),
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
        if normalized_schema not in {"query_normalization", "intent_routing", "livestock_triage"}:
            return _backend_failure(
                request,
                self.provider,
                payload,
                started,
                error_code="LOCAL_MODEL_SCHEMA_UNSUPPORTED",
                reason="transformers backend currently supports query_normalization and intent_routing only",
            )

        prompt = _prompt_for_schema(request.prompt, normalized_schema)
        try:
            generation = await asyncio.wait_for(
                asyncio.to_thread(self._generate_with_usage, prompt, request),
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

        raw_text = generation.text
        content = parse_local_json_response(raw_text, normalized_schema)
        content = _normalize_schema_content(content, normalized_schema)
        return LocalBackendResponse(
            status=str(content.get("status", "success")),
            schema_name=normalized_schema,
            content=content,
            fallback_required=bool(content.get("fallback_required")),
            provider=self.provider,
            latency_ms=_latency_ms(started),
            usage=generation.usage,
            raw_text=raw_text,
            error_code=content.get("error_code"),
            reason=content.get("reason"),
            request_payload=payload,
        )

    def _generate_text(self, prompt: str, request: LocalBackendRequest) -> str:
        return self._generate_with_usage(prompt, request).text

    def _generate_with_usage(self, prompt: str, request: LocalBackendRequest) -> LocalGeneration:
        if self._generator is not None:
            return LocalGeneration(text=self._generator(prompt, request))

        if self._model is None or self._tokenizer is None or self._loaded_model_name != request.model:
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as exc:
                raise ImportError(
                    "install local transformers dependencies with: pip install -e .[transformers]"
                ) from exc

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
                "content": _system_prompt_for_schema(request.schema_name),
            },
            {"role": "user", "content": prompt},
        ]
        if hasattr(tokenizer, "apply_chat_template"):
            template_output = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
            )
            input_ids, attention_mask = _extract_tokenized_inputs(template_output)
            model_device = getattr(model, "device", None)
            if model_device is not None and hasattr(input_ids, "to"):
                input_ids = input_ids.to(model_device)
            if model_device is not None and attention_mask is not None and hasattr(attention_mask, "to"):
                attention_mask = attention_mask.to(model_device)
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
        return LocalGeneration(
            text=tokenizer.decode(generated_ids, skip_special_tokens=True).strip(),
            usage=tokenizer_usage(len(input_ids[0]), len(generated_ids)),
        )


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


def _ollama_options(options: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    if "temperature" in options:
        mapped["temperature"] = options["temperature"]
    if "max_new_tokens" in options:
        mapped["num_predict"] = options["max_new_tokens"]
    return mapped


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


def _intent_routing_prompt(query: str) -> str:
    return (
        "Classify the livestock user question. "
        "Return exactly one JSON object with keys: status, intent, confidence, should_use_rag, should_use_tools, reason, fallback_required. "
        "Allowed intents: assistant_intro, general_qa, disease_consultation, measurement_analysis, out_of_scope. "
        "Use disease_consultation for animal symptoms, disease, fever, diarrhea, cough, appetite changes, or health risk. "
        "Use general_qa for livestock management or knowledge questions. "
        "Use assistant_intro only for greeting or asking what the assistant can do. "
        "Use out_of_scope for non-livestock requests. "
        "Set should_use_rag=true for general_qa and disease_consultation. "
        'Example: {"status":"success","intent":"disease_consultation","confidence":0.9,'
        '"should_use_rag":true,"should_use_tools":["disease_agent"],"reason":"animal symptoms","fallback_required":false}\n'
        f"User question: {query.strip()}"
    )


def _livestock_triage_prompt(query: str) -> str:
    example = (
        '{"status":"success","schema_name":"livestock_triage","fallback_required":false,'
        '"intent_candidate":"disease_consultation","confidence":0.9,'
        '"slots":[{"name":"species","value":"犊牛","confidence":1.0,"source_span":"犊牛"},'
        '{"name":"duration_days","value":2,"confidence":1.0,"source_span":"两天"},'
        '{"name":"temperature_c","value":40.2,"confidence":1.0,"source_span":"40.2度"},'
        '{"name":"group_outbreak","value":false,"confidence":1.0,"source_span":"没有群体发病"}],'
        '"risk_candidate":"medium","risk_signals":["发热","腹泻"]}'
        if any("\u4e00" <= char <= "\u9fff" for char in query)
        else (
            '{"status":"success","schema_name":"livestock_triage","fallback_required":false,'
            '"intent_candidate":"disease_consultation","confidence":0.9,'
            '"slots":[{"name":"species","value":"calf","confidence":1.0,"source_span":"calf"},'
            '{"name":"duration_days","value":2,"confidence":1.0,"source_span":"2 days"},'
            '{"name":"temperature_c","value":40.2,"confidence":1.0,"source_span":"40.2 C"}],'
            '"risk_candidate":"medium","risk_signals":["fever","diarrhea"]}'
        )
    )
    return (
        "Classify one livestock user message without answering it. "
        "Return exactly one JSON object with status, schema_name, fallback_required, intent_candidate, confidence, "
        "slots, risk_candidate, and risk_signals. Allowed intents: assistant_intro, general_qa, disease_consultation, "
        "measurement_analysis, out_of_scope. Slots may only use species, age_stage, duration_days, temperature_c, "
        "temperature_status, appetite_status, feces_status, respiratory_status, or group_outbreak; every slot must have "
        "name, value, confidence, and an exact source_span copied from the user message. Include every explicitly "
        "stated supported slot, including group_outbreak=false when an outbreak is negated. String slot values must "
        "appear verbatim in source_span; never translate them. risk_signals must be strings. "
        "Set status to success, schema_name exactly to livestock_triage, and fallback_required to false. "
        "Do not diagnose or recommend treatment. Use low for management questions without symptoms; medium for an "
        "individual animal with symptoms or fever; high for a non-negated group outbreak or food-chain concern; "
        "emergency for requests for an exact drug dose or withdrawal period. A negated outbreak is not high risk. "
        f"Example: {example}\n"
        f"User message: {query.strip()}"
    )


def _prompt_for_schema(query: str, schema_name: str) -> str:
    if schema_name == "intent_routing":
        return _intent_routing_prompt(query)
    if schema_name == "livestock_triage":
        return _livestock_triage_prompt(query)
    return _query_normalization_prompt(query)


def _system_prompt_for_schema(schema_name: str) -> str:
    normalized = schema_name.strip().lower()
    if normalized == "intent_routing":
        return (
            "You route livestock assistant messages. Return exactly one JSON object and no prose. "
            "Never answer the user; only classify the message."
        )
    if normalized == "livestock_triage":
        return (
            "You classify livestock messages into intent, source-grounded slots, and risk. "
            "Return exactly one JSON object and no prose. Set schema_name exactly to livestock_triage. "
            "Never diagnose, prescribe, or answer the user."
        )
    return (
        "You normalize livestock questions for retrieval. "
        "Return exactly one JSON object and no prose. "
        "Set fallback_required to false when you can produce a normalized query."
    )


def _normalize_schema_content(content: dict[str, Any], schema_name: str) -> dict[str, Any]:
    content["schema_name"] = schema_name
    if schema_name == "intent_routing":
        return _normalize_intent_routing_content(content)
    if schema_name == "livestock_triage":
        if content.get("status") == "success" and content.get("intent_candidate"):
            content["fallback_required"] = False
        return content
    if schema_name != "query_normalization":
        return content
    if content.get("status") == "success" and str(content.get("normalized_query", "")).strip():
        content["fallback_required"] = False
    return content


def _normalize_intent_routing_content(content: dict[str, Any]) -> dict[str, Any]:
    if content.get("status") == "success" and content.get("intent"):
        content["fallback_required"] = False
    if "should_use_tools" not in content:
        content["should_use_tools"] = []
    return content


def _extract_tokenized_inputs(template_output: Any) -> tuple[Any, Any | None]:
    getter = getattr(template_output, "get", None)
    if callable(getter):
        input_ids = getter("input_ids")
        if input_ids is not None:
            return input_ids, getter("attention_mask")
    return template_output, None


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
