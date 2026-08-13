"""LangGraph workflow for grounded generation and independent verification."""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.clients.colab_llm import ColabLLMClient
from app.database.poc_store import TextToSQLService, search_documents


class QAState(TypedDict, total=False):
    question: str
    attachment_context: str
    sql_context: str
    sql_used: str
    document_context: str
    sources: list[str]
    draft: str
    approved: bool
    issues: list[str]
    revised_answer: str
    final_answer: str


async def retrieve_context(state: QAState) -> dict[str, Any]:
    sql_result = TextToSQLService().execute(state["question"])
    documents = search_documents(state["question"])
    document_context = "\n\n".join(
        f"[문서: {item['title']}]\n{item['content']}" for item in documents
    )[:3_500]
    sql_context = sql_result.as_context()[:4_000] if sql_result else "조회된 정형 데이터 없음"
    return {
        "sql_context": sql_context,
        "sql_used": sql_result.sql if sql_result else "",
        "document_context": document_context or "검색된 내부 문서 없음",
        "sources": sorted({item["title"] for item in documents}),
    }


async def generate_answer(state: QAState) -> dict[str, str]:
    prompt = f"""다음 근거만 사용해 한국어로 여신심사 답변을 작성하세요.
확인되지 않은 사실은 단정하지 말고, 금액 단위가 데이터에 명시되지 않았다면 '데이터 기준 단위'라고 표현하세요.
답변에 '판단', '근거', '주요 위험요인', '추가 확인사항'을 구분하세요.

[질문]
{state['question']}
[정형 DB 조회 결과]
{state.get('sql_context', '')}
[내부 문서 RAG 결과]
{state.get('document_context', '')}
[사용자 첨부자료]
{state.get('attachment_context', '') or '없음'}
"""
    draft = await ColabLLMClient().complete(
        [
            {"role": "system", "content": "당신은 생성 에이전트 A입니다. 근거 중심의 여신심사 답변을 작성합니다."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1200,
    )
    return {"draft": draft}


async def validate_answer(state: QAState) -> dict[str, Any]:
    prompt = f"""당신은 독립 검증 에이전트 B입니다. 생성 에이전트 A의 답변을 검증하세요.
검증 항목: 근거 일치, 수치 정확성, 근거 없는 단정, 질문 충족, 중요 위험 누락.
문제가 있으면 답변을 직접 고친 완성본을 revised_answer에 넣으세요.
반드시 JSON 하나만 반환하세요.
{{"approved": true, "issues": [], "revised_answer": ""}}

[정형 근거]
{state.get('sql_context', '')}
[문서 근거]
{state.get('document_context', '')}
[첨부 근거]
{state.get('attachment_context', '')}
[A의 답변]
{state.get('draft', '')}
"""
    raw = await ColabLLMClient().complete(
        [
            {"role": "system", "content": "당신은 생성 결과를 엄격히 검증하고 필요하면 수정하는 검증 에이전트 B입니다."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1400,
    )
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0) if match else raw)
        approved = bool(parsed.get("approved"))
        revised = str(parsed.get("revised_answer") or "").strip()
        issues = [str(item) for item in parsed.get("issues", [])]
    except (json.JSONDecodeError, AttributeError, TypeError):
        approved, revised, issues = True, "", ["검증 응답을 구조화하지 못해 원문을 유지했습니다."]
    if not approved and not revised:
        revised = state["draft"] + "\n\n※ 검증 에이전트가 추가 근거 확인이 필요하다고 판단했습니다."
    return {"approved": approved, "issues": issues, "revised_answer": revised}


async def finalize_answer(state: QAState) -> dict[str, str]:
    answer = state.get("draft", "") if state.get("approved") else state.get("revised_answer", "")
    if state.get("sources"):
        answer += "\n\n참조 문서: " + ", ".join(state["sources"])
    return {"final_answer": answer}


def build_graph():
    workflow = StateGraph(QAState)
    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("generator_a", generate_answer)
    workflow.add_node("validator_b", validate_answer)
    workflow.add_node("finalize", finalize_answer)
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "generator_a")
    workflow.add_edge("generator_a", "validator_b")
    workflow.add_edge("validator_b", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile()


qa_graph = build_graph()


async def run_qa(question: str, attachment_context: str = "") -> QAState:
    return await qa_graph.ainvoke({"question": question, "attachment_context": attachment_context})
