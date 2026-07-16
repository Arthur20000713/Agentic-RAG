from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _client() -> TestClient:
    settings = Settings(database={"url": "sqlite:///:memory:"})
    return TestClient(create_app(settings=settings))


def test_frontend_chat_page_static_contract() -> None:
    response = _client().get("/app")

    assert response.status_code == 200
    assert 'id="chat-form"' in response.text
    assert 'id="chat-query"' in response.text
    assert 'id="new-chat-button"' in response.text
    assert 'data-view="chat"' in response.text
    assert 'id="conversation-list"' in response.text
    assert 'id="conversation-search"' in response.text
    assert 'id="sidebar-toggle"' in response.text
    assert 'aria-label="对话历史"' in response.text
    assert 'src="./app.js?v=9"' in response.text


def test_frontend_chat_js_contract() -> None:
    response = _client().get("/app/app.js")

    assert response.status_code == 200
    assert "function renderChat" in response.text
    assert "async function submitChat" in response.text
    assert 'fetch("/api/chat"' in response.text
    assert "chatSessionId" in response.text
    assert "form.dataset.sessionId" in response.text
    assert "risk_level" in response.text
    assert "follow_up_questions" in response.text
    assert "AbortController" in response.text
    assert "payload.code !== 0" in response.text
    assert "请求超时，请稍后重试。" in response.text
    assert "function startNewChatSession" in response.text
    assert "function parseConversationDate" in response.text
    assert 'chatQuery.addEventListener("keydown"' in response.text
    assert 'event.key === "Enter"' in response.text
    assert "!event.shiftKey" in response.text
    assert "!event.isComposing" in response.text
    assert "chatForm.requestSubmit()" in response.text
    assert "function renderMarkdown" in response.text
    assert "function sanitizeMarkdownUrl" in response.text
    assert 'class="answer-text markdown-body"' in response.text
    assert "conversationPageSize" in response.text
    assert "options.append === true" in response.text
    assert "history-load-more" in response.text
    assert 'fetch(`/api/conversations/${encodeURIComponent(sessionId)}`' in response.text
    assert 'method: "PATCH"' in response.text
    assert 'method: "DELETE"' in response.text
    assert '"X-Client-ID": state.clientId' in response.text
    assert "CLIENT_ID_STORAGE_KEY" in response.text
    assert "livestock_agentic_rag_client_id" in response.text
    assert "user_id: state.clientId" in response.text
    assert "function renderConversationList" in response.text
    assert "function renderStoredMessage" in response.text
    assert "function renderMessageErrors" in response.text
    assert "function openConversation" in response.text
    assert "function beginConversationRename" in response.text
    assert "function deleteConversation" in response.text
    assert "function toggleSidebar" in response.text
    assert 'event.key === "Escape"' in response.text
    assert "window.confirm" in response.text
    assert "conversationLoadToken" in response.text
    assert "conversationListToken" in response.text
    assert "chatRequestToken" in response.text
    assert "requestSessionId" in response.text
    assert "state.chatSessionId !== requestSessionId" in response.text
    assert "cancelActiveChatRequest" in response.text
    assert 'setFormDisabled(document.querySelector("#chat-form"), false)' in response.text
    assert "handleConversationListKeydown" in response.text
    assert "clearMissing: true" in response.text
    assert "error.code === 40004" in response.text
    assert "setFormDisabled(form, true)" in response.text
    assert "loadToken === state.conversationLoadToken" in response.text


def test_frontend_markdown_styles_contract() -> None:
    response = _client().get("/app/styles.css")

    assert response.status_code == 200
    assert ".markdown-body" in response.text
    assert ".markdown-body pre" in response.text
    assert ".markdown-body blockquote" in response.text
    assert ".conversation-history" in response.text
    assert ".conversation-item.is-current" in response.text
    assert ".conversation-menu" in response.text
    assert ".sidebar-collapsed" in response.text
    assert ".history-load-more" in response.text


def test_conversation_history_items_use_a_single_line() -> None:
    client = _client()

    html = client.get("/app").text
    css = client.get("/app/styles.css").text
    normalized_css = css.replace("\r\n", "\n")

    assert 'href="./styles.css?v=10"' in html
    assert ".conversation-preview,\n.conversation-open time {\n  display: none;" in normalized_css


def test_frontend_sources_and_tools_contract() -> None:
    client = _client()

    js = client.get("/app/app.js").text
    chat = client.post("/api/chat", json={"query": "How should cattle feeding be managed?"}).json()

    assert "function renderSources" in js
    assert "function renderToolSummary" in js
    assert "source_uri" in js
    assert "tools_used" in js
    assert chat["data"]["sources"][0]["source_uri"].startswith("rag://")
    assert "livestock_rag_search" in chat["data"]["tools_used"]


def test_frontend_measurement_contract() -> None:
    client = _client()

    html = client.get("/app").text
    js = client.get("/app/app.js").text
    response = client.post(
        "/api/measurement/analyze",
        json={
            "animal_id": "yak_032",
            "current": {"chest_girth_cm": 158.4},
            "confidence": 0.82,
            "use_demo_history": True,
        },
    ).json()

    assert 'id="measurement-form"' in html
    assert 'id="measurement-result"' in html
    assert "function renderMeasurement" in js
    assert "async function submitMeasurement" in js
    assert 'fetch("/api/measurement/analyze"' in js
    assert "abnormal_items" in js
    assert response["data"]["report"]
    assert response["data"]["evidence"]


def test_frontend_debug_panel_contract() -> None:
    client = _client()

    html = client.get("/app").text
    js = client.get("/app/app.js").text
    trace = client.get("/api/traces/req_debug").json()
    rag_status = client.get("/api/rag/status").json()

    assert 'id="debug-json"' in html
    assert 'id="debug-summary"' in html
    assert "function renderDebugPanel" in js
    assert "function buildDebugSummary" in js
    assert "function renderDebugSummary" in js
    assert "function renderRagStatus" in js
    assert 'fetch("/api/rag/status"' in js
    for field in (
        "request_id",
        "rag_mode",
        "agent_path",
        "safety",
        "verifier",
        "v3_debug_summary",
        "rag_status",
        "collection",
        "batch_id",
        "quality_gate_status",
    ):
        assert field in js
    assert trace["data"]["request_id"] == "req_debug"
    assert "agent_trace" in trace["data"]
    assert "v3_debug_summary" in trace["data"]
    assert rag_status["data"]["rag_mode"] == "fake"


def test_frontend_debug_panel_can_show_v3_debug_payload() -> None:
    client = _client()

    js = client.get("/app/app.js").text
    chat = client.post("/api/chat", json={"query": "How should cattle feeding be managed?"}).json()

    assert "v3_debug" in chat["data"]
    assert chat["data"]["v3_debug"]["v3_enabled"] is False
    assert "flags" in js
    assert "route" in js
    assert "memory" in js
    assert "raw" in js
