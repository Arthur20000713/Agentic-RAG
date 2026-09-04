from __future__ import annotations

import asyncio
from typing import Any

from backend.app.model.local_backends import (
    LocalBackendRequest,
    OllamaBackend,
    TransformersBackend,
)
from backend.app.model.local_schema import parse_local_json_response


def test_parse_local_json_response_adds_schema_metadata() -> None:
    result = parse_local_json_response('{"normalized_query": "calf feed"}', schema_name="query_normalization")

    assert result == {
        "normalized_query": "calf feed",
        "status": "success",
        "schema_name": "query_normalization",
        "fallback_required": False,
    }


def test_parse_local_json_response_returns_fallback_for_non_json_text() -> None:
    result = parse_local_json_response("not json", schema_name="slot_extraction")

    assert result["status"] == "error"
    assert result["schema_name"] == "slot_extraction"
    assert result["fallback_required"] is True
    assert result["error_code"] == "LOCAL_MODEL_SCHEMA_ERROR"


def test_parse_local_json_response_extracts_json_from_model_text() -> None:
    result = parse_local_json_response(
        'Sure:\n```json\n{"normalized_query": "calf weaning feed", "language": "en"}\n```',
        schema_name="query_normalization",
    )

    assert result["status"] == "success"
    assert result["normalized_query"] == "calf weaning feed"


def test_ollama_backend_builds_json_generation_payload() -> None:
    captured: dict[str, Any] = {}

    def fake_transport(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return {
            "response": '{"normalized_query": "weaning feed"}',
            "prompt_eval_count": 12,
            "eval_count": 4,
        }

    backend = OllamaBackend(transport=fake_transport)
    request = LocalBackendRequest(
        prompt="weaning feed",
        schema_name="query_normalization",
        endpoint="http://127.0.0.1:11434",
        model="qwen2.5:7b-instruct",
        timeout_seconds=8,
        options={"temperature": 0.0, "max_new_tokens": 96, "device": "auto"},
    )

    response = asyncio.run(backend.generate(request))

    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert captured["timeout_seconds"] == 8
    assert captured["payload"]["model"] == "qwen2.5:7b-instruct"
    assert "Normalize the livestock user question" in captured["payload"]["prompt"]
    assert "Return exactly one JSON object" in captured["payload"]["system"]
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["options"] == {
        "seed": 0,
        "temperature": 0.0,
        "num_predict": 96,
    }
    assert response.status == "success"
    assert response.fallback_required is False
    assert response.content["normalized_query"] == "weaning feed"
    assert response.usage.model_dump() == {
        "source": "provider",
        "input_tokens": 12,
        "output_tokens": 4,
        "total_tokens": 16,
    }


def test_ollama_backend_returns_structured_timeout_failure() -> None:
    def timeout_transport(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        raise TimeoutError("slow local model")

    backend = OllamaBackend(transport=timeout_transport)
    request = LocalBackendRequest(
        prompt="extract slots",
        schema_name="slot_extraction",
        endpoint="http://127.0.0.1:11434",
        model="qwen2.5:7b-instruct",
        timeout_seconds=1,
    )

    response = asyncio.run(backend.generate(request))

    assert response.status == "error"
    assert response.fallback_required is True
    assert response.error_code == "LOCAL_MODEL_TIMEOUT"
    assert response.content["fallback_required"] is True


def test_ollama_backend_builds_livestock_triage_prompt() -> None:
    captured: dict[str, Any] = {}

    def fake_transport(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        captured.update(payload)
        return {
            "response": (
                '{"status":"success","schema_name":"livestock_triage",'
                '"fallback_required":false,"intent_candidate":"general_qa",'
                '"confidence":0.9,"slots":[],"risk_candidate":"low","risk_signals":[]}'
            )
        }

    response = asyncio.run(
        OllamaBackend(transport=fake_transport).generate(
            LocalBackendRequest(
                prompt="calf feeding",
                schema_name="livestock_triage",
                endpoint="http://127.0.0.1:11434",
                model="qwen2.5:7b",
            )
        )
    )

    assert "schema_name exactly to livestock_triage" in captured["prompt"]
    assert "schema_name exactly to livestock_triage" in captured["system"]
    assert response.content["schema_name"] == "livestock_triage"
    assert response.fallback_required is False


def test_transformers_backend_builds_query_normalization_prompt() -> None:
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, request: LocalBackendRequest) -> str:
        captured["prompt"] = prompt
        captured["request"] = request
        return '{"status":"success","normalized_query":"calf weaning feed","language":"en","fallback_required":false}'

    backend = TransformersBackend(generator=fake_generator)
    request = LocalBackendRequest(
        prompt="  Calf after weaning feed?  ",
        schema_name="query_normalization",
        endpoint="",
        model="Qwen/Qwen2.5-0.5B-Instruct",
        timeout_seconds=8,
        options={"device": "auto", "torch_dtype": "auto", "max_new_tokens": 96, "temperature": 0},
    )

    response = asyncio.run(backend.generate(request))

    assert "Normalize the livestock user question" in str(captured["prompt"])
    assert "fallback_required=false" in str(captured["prompt"])
    assert response.status == "success"
    assert response.provider == "transformers"
    assert response.content["normalized_query"] == "calf weaning feed"
    assert response.usage.source == "unavailable"


def test_transformers_backend_normalizes_successful_query_fallback_flag() -> None:
    backend = TransformersBackend(
        generator=lambda prompt, request: (
            '{"status":"success","normalized_query":"feed for calf after weaning",'
            '"language":"en","fallback_required":true}'
        )
    )
    request = LocalBackendRequest(
        prompt="What feed should I use for a calf after weaning?",
        schema_name="query_normalization",
        endpoint="",
        model="Qwen/Qwen2.5-0.5B-Instruct",
    )

    response = asyncio.run(backend.generate(request))

    assert response.status == "success"
    assert response.fallback_required is False
    assert response.content["fallback_required"] is False


def test_transformers_backend_builds_intent_routing_prompt() -> None:
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, request: LocalBackendRequest) -> str:
        captured["prompt"] = prompt
        captured["request"] = request
        return (
            '{"status":"success","intent":"disease_consultation","confidence":0.91,'
            '"should_use_rag":true,"should_use_tools":["disease_agent"],'
            '"reason":"livestock symptoms","fallback_required":false}'
        )

    backend = TransformersBackend(generator=fake_generator)
    request = LocalBackendRequest(
        prompt="calf diarrhea and fever",
        schema_name="intent_routing",
        endpoint="",
        model="Qwen/Qwen2.5-0.5B-Instruct",
    )

    response = asyncio.run(backend.generate(request))

    assert "Classify the livestock user question" in str(captured["prompt"])
    assert "assistant_intro" in str(captured["prompt"])
    assert response.status == "success"
    assert response.provider == "transformers"
    assert response.content["intent"] == "disease_consultation"
    assert response.content["fallback_required"] is False


def test_transformers_backend_builds_livestock_triage_prompt() -> None:
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, request: LocalBackendRequest) -> str:
        captured["prompt"] = prompt
        captured["request"] = request
        return (
            '{"status":"success","schema_name":"livestock_triage","fallback_required":false,'
            '"intent_candidate":"disease_consultation","confidence":0.91,"slots":[],'
            '"risk_candidate":"medium","risk_signals":["fever"]}'
        )

    backend = TransformersBackend(generator=fake_generator)
    request = LocalBackendRequest(
        prompt="calf fever 40.2C",
        schema_name="livestock_triage",
        endpoint="",
        model="Qwen/Qwen2.5-0.5B-Instruct",
    )

    response = asyncio.run(backend.generate(request))

    assert "source_span" in str(captured["prompt"])
    assert "do not diagnose" in str(captured["prompt"]).casefold()
    assert str(captured["prompt"]).count("Classify one livestock user message") == 1
    assert str(captured["prompt"]).endswith("User message: calf fever 40.2C")
    assert response.status == "success"
    assert response.content["intent_candidate"] == "disease_consultation"
    assert response.content["fallback_required"] is False


def test_transformers_backend_accepts_chat_template_batch_encoding() -> None:
    class FakeTensor:
        def __init__(self, values: list[int]) -> None:
            self.values = values

        def to(self, device: str):
            return self

        def __getitem__(self, index):
            if isinstance(index, slice):
                return self.values[index]
            return self.values

    class FakeTokenizer:
        def apply_chat_template(self, messages, add_generation_prompt: bool, return_tensors: str):
            return {
                "input_ids": FakeTensor([1, 2]),
                "attention_mask": FakeTensor([1, 1]),
            }

        def decode(self, generated_ids, skip_special_tokens: bool) -> str:
            return '{"status":"success","normalized_query":"calf feed","language":"en","fallback_required":false}'

    class FakeModel:
        device = "cuda:0"

        def __init__(self) -> None:
            self.received_attention_mask = None

        def generate(self, input_ids, **kwargs):
            assert not isinstance(input_ids, dict)
            self.received_attention_mask = kwargs.get("attention_mask")
            return [FakeTensor([1, 2, 3])]

    backend = TransformersBackend()
    model = FakeModel()
    backend._tokenizer = FakeTokenizer()
    backend._model = model
    backend._loaded_model_name = "Qwen/Qwen2.5-0.5B-Instruct"
    request = LocalBackendRequest(
        prompt="calf feed",
        schema_name="query_normalization",
        endpoint="",
        model="Qwen/Qwen2.5-0.5B-Instruct",
    )

    response = asyncio.run(backend.generate(request))

    assert "calf feed" in (response.raw_text or "")
    assert model.received_attention_mask is not None
    assert response.usage.model_dump() == {
        "source": "tokenizer",
        "input_tokens": 2,
        "output_tokens": 1,
        "total_tokens": 3,
    }


def test_transformers_backend_rejects_unsupported_schema() -> None:
    backend = TransformersBackend(generator=lambda prompt, request: "{}")
    request = LocalBackendRequest(
        prompt="extract slots",
        schema_name="slot_extraction",
        endpoint="",
        model="Qwen/Qwen2.5-0.5B-Instruct",
    )

    response = asyncio.run(backend.generate(request))

    assert response.status == "error"
    assert response.fallback_required is True
    assert response.error_code == "LOCAL_MODEL_SCHEMA_UNSUPPORTED"
