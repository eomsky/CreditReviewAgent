"""Case-scoped LangGraph workflow with iterative generation and validation."""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.clients.colab_llm import ColabLLMClient
from app.database.poc_store import TextToSQLService, record_agent_event, search_documents

MAX_REVISION_COUNT = 2


class QAState(TypedDict, total=False):
    question: str
    case_id: str
    conversation_id: str
    attachment_context: str
    sql_context: str
    sql_used: str
    document_context: str
    sources: list[str]
    draft: str
    revised_draft: str
    revision_count: int
    validation_issues: list[str]
    validation_history: list[dict[str, Any]]
    approved: bool
    final_answer: str


def _event(state: QAState, agent: str, event_type: str, content: str = "") -> None:
    case_id = state.get("case_id")
    if case_id:
        record_agent_event(
            case_id, state.get("conversation_id"), agent, event_type, content, state.get("sources", [])
        )


async def retrieve_context(state: QAState) -> dict[str, Any]:
    sql_result = TextToSQLService().execute(state["question"])
    documents = search_documents(state["question"], case_id=state.get("case_id"))
    document_context = "\n\n".join(
        f"[문서: {item['title']}]\n{item['content']}" for item in documents
    )[:3_500]
    sql_context = sql_result.as_context()[:4_000] if sql_result else "조회된 정형 데이터 없음"
    sources = sorted({item["title"] for item in documents})
    result = {
        "sql_context": sql_context,
        "sql_used": sql_result.sql if sql_result else "",
        "document_context": document_context or "검색된 내부 문서 없음",
        "sources": sources,
        "revision_count": 0,
        "validation_history": [],
    }
    _event({**state, **result}, "generator", "generator.retrieve", sql_result.sql if sql_result else "RAG 조회")
    return result


async def generate_answer(state: QAState) -> dict[str, str]:
    prompt = f"""다음 근거만 사용해 한국어로 여신심사 답변을 작성하세요.
확인되지 않은 사실은 단정하지 말고, 답변에 판단·근거·주요 위험요인·추가 확인사항을 구분하세요.

[질문]\n{state['question']}
[정형 DB]\n{state.get('sql_context', '')}
[현재 심사건 및 공통 문서]\n{state.get('document_context', '')}
[첨부자료]\n{state.get('attachment_context', '') or '없음'}
"""
    draft = await ColabLLMClient().complete(
        [
            {"role": "system", "content": "당신은 생성 에이전트입니다. 근거 중심의 여신심사 답변을 작성합니다."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1200,
    )
    _event(state, "generator", "generator.draft_created", draft)
    return {"draft": draft, "revised_draft": draft}


async def revise_answer(state: QAState) -> dict[str, Any]:
    revision_count = state.get("revision_count", 0) + 1
    prompt = f"""검증 이슈를 모두 해결하도록 여신심사 답변을 수정하세요. 근거 밖의 내용을 추가하지 마세요.
[질문]\n{state['question']}
[근거]\n{state.get('sql_context', '')}\n{state.get('document_context', '')}
[현재 답변]\n{state.get('revised_draft') or state.get('draft', '')}
[검증 이슈]\n{json.dumps(state.get('validation_issues', []), ensure_ascii=False)}
"""
    revised = await ColabLLMClient().complete(
        [
            {"role": "system", "content": "당신은 검증 의견을 반영하는 생성 에이전트입니다."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1300,
    )
    _event(state, "generator", "generator.revision_created", revised)
    return {"revised_draft": revised, "revision_count": revision_count}


async def validate_answer(state: QAState) -> dict[str, Any]:
    _event(state, "validator", "validator.validation_started")
    candidate = state.get("revised_draft") or state.get("draft", "")
    prompt = f"""독립 검증 에이전트로서 답변을 검증하세요.
검증 항목: 근거 일치, 수치 정확성, 근거 없는 단정, 질문 충족, 중요 위험 누락.
반드시 JSON 하나만 반환하세요: {{"approved": true, "issues": []}}
[정형 근거]\n{state.get('sql_context', '')}
[문서 근거]\n{state.get('document_context', '')}
[첨부 근거]\n{state.get('attachment_context', '')}
[답변]\n{candidate}
"""
    raw = await ColabLLMClient().complete(
        [
            {"role": "system", "content": "당신은 엄격한 독립 검증 에이전트입니다."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=700,
    )
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0) if match else raw)
        approved = bool(parsed.get("approved"))
        issues = [str(item) for item in parsed.get("issues", [])]
    except (json.JSONDecodeError, AttributeError, TypeError):
        approved, issues = False, ["검증 응답을 구조화하지 못했습니다."]
    history = [*state.get("validation_history", []), {"approved": approved, "issues": issues}]
    _event(state, "validator", "validator.approved" if approved else "validator.validation_failed", "; ".join(issues))
    return {"approved": approved, "validation_issues": issues, "validation_history": history}


def route_validation(state: QAState) -> str:
    if state.get("approved") or state.get("revision_count", 0) >= MAX_REVISION_COUNT:
        return "finalize"
    return "revise"


async def finalize_answer(state: QAState) -> dict[str, str]:
    answer = state.get("revised_draft") or state.get("draft", "")
    if not state.get("approved"):
        answer += "\n\n※ 최대 수정 횟수에 도달하여 담당자의 추가 확인이 필요합니다."
    _event(state, "system", "finalized", answer)
    return {"final_answer": answer}


def build_graph():
    workflow = StateGraph(QAState)
    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("generate", generate_answer)
    workflow.add_node("validate", validate_answer)
    workflow.add_node("revise", revise_answer)
    workflow.add_node("finalize", finalize_answer)
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", "validate")
    workflow.add_conditional_edges("validate", route_validation, {"revise": "revise", "finalize": "finalize"})
    workflow.add_edge("revise", "validate")
    workflow.add_edge("finalize", END)
    return workflow.compile()


qa_graph = build_graph()


async def run_qa(
    question: str,
    attachment_context: str = "",
    case_id: str = "",
    conversation_id: str = "",
) -> QAState:
    return await qa_graph.ainvoke(
        {
            "question": question,
            "attachment_context": attachment_context,
            "case_id": case_id,
            "conversation_id": conversation_id,
        }
    )