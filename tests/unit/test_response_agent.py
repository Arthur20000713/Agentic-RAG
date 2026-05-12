from __future__ import annotations

from backend.app.agent.response_agent import ResponseAgent
from backend.app.agent.state import MultiAgentState


def test_response_agent_renders_safe_answer_and_sources() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="general_qa",
        evidence_status="success",
        final_answer="根据资料，犊牛腹泻需要结合体温和精神状态评估。",
        safety_result={
            "passed": True,
            "violations": [],
            "message": "passed",
            "safe_answer": "根据资料，犊牛腹泻需要结合体温和精神状态评估。",
        },
        verification_result={"passed": True, "issues": []},
        tool_results={
            "livestock_rag_search": {
                "status": "success",
                "hits": [
                    {
                        "chunk_id": "doc_001_chunk_012",
                        "document_id": "doc_001",
                        "document_title": "犊牛腹泻防治技术手册",
                        "source_uri": "rag://default/doc_001/doc_001_chunk_012",
                    }
                ],
                "citations": [
                    {
                        "source_id": "doc_001",
                        "title": "犊牛腹泻防治技术手册",
                        "page": 12,
                        "section_title": "常见病因",
                        "chunk_id": "doc_001_chunk_012",
                    }
                ],
                "mapping_warnings": [],
            },
            "safety_agent": {"passed": True},
            "verifier_agent": {"passed": True},
        },
    )

    updated = ResponseAgent().render(state)

    assert updated is state
    assert state.active_agent == "response_agent"
    assert state.final_answer is not None
    assert "参考来源" in state.final_answer
    assert "rag://default/doc_001/doc_001_chunk_012" in state.final_answer
    response = state.tool_results["response_agent"]
    assert response["answer"] == state.final_answer
    assert response["safe_answer"] == "根据资料，犊牛腹泻需要结合体温和精神状态评估。"
    assert response["sources"][0]["source_uri"] == "rag://default/doc_001/doc_001_chunk_012"
    assert response["tools_used"] == [
        "livestock_rag_search",
        "safety_agent",
        "verifier_agent",
        "response_agent",
    ]
    assert state.agent_trace[-1]["node"] == "response_agent"
    assert state.agent_trace[-1]["source_count"] == 1


def test_response_agent_does_not_fabricate_sources_for_low_confidence() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="unknown",
        intent="general_qa",
        evidence_status="low_confidence",
        final_answer="当前知识库中没有检索到足够依据，无法给出确定回答。",
        safety_result={
            "passed": True,
            "safe_answer": "当前知识库中没有检索到足够依据，无法给出确定回答。",
        },
        tool_results={
            "livestock_rag_search": {
                "status": "low_confidence",
                "hits": [{"chunk_id": "chunk_1", "source_uri": "rag://default/doc/chunk"}],
                "citations": [{"source_uri": "rag://default/doc/chunk", "title": "Doc"}],
            }
        },
    )

    ResponseAgent().render(state)

    response = state.tool_results["response_agent"]
    assert response["sources"] == []
    assert "参考来源" not in (state.final_answer or "")
    assert response["answer"] == "当前知识库中没有检索到足够依据，无法给出确定回答。"


def test_response_agent_keeps_blocked_safety_answer_without_sources_append() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        evidence_status="success",
        draft_answer="确诊为肺炎，使用药物 5 mg/kg。",
        final_answer="安全提示：不能提供具体药物剂量、处方或确定性诊断。建议尽快联系执业兽医。",
        safety_result={
            "passed": False,
            "violations": ["dosage", "definitive_diagnosis"],
            "safe_answer": "安全提示：不能提供具体药物剂量、处方或确定性诊断。建议尽快联系执业兽医。",
        },
        tool_results={
            "livestock_rag_search": {
                "status": "success",
                "hits": [{"chunk_id": "chunk_1", "source_uri": "rag://default/doc/chunk"}],
                "citations": [{"source_uri": "rag://default/doc/chunk", "title": "Doc"}],
            },
            "safety_agent": {"passed": False},
        },
    )

    ResponseAgent().render(state)

    assert state.final_answer == "安全提示：不能提供具体药物剂量、处方或确定性诊断。建议尽快联系执业兽医。"
    assert "参考来源" not in state.final_answer
    assert "5 mg/kg" not in state.final_answer
    assert state.tool_results["response_agent"]["sources"][0]["source_uri"] == "rag://default/doc/chunk"


def test_response_agent_uses_draft_fallback_when_safety_result_missing() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="body measurement",
        intent="measurement_analysis",
        draft_answer="个体 yak_001 当前体尺已记录。无历史记录，不能判断增长趋势。",
    )

    ResponseAgent().render(state)

    assert state.final_answer == "个体 yak_001 当前体尺已记录。无历史记录，不能判断增长趋势。"
    assert state.tool_results["response_agent"]["sources"] == []
    assert state.tool_results["response_agent"]["tools_used"] == ["response_agent"]
