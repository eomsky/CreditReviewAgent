"""Grounded conversational endpoint with persistence, RAG, agents, and guardrails."""

from __future__ import annotations

import json
import base64
import binascii
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.clients.colab_llm import ColabLLMClient
from app.core.config import settings
from app.database.poc_store import ensure_conversation, ensure_default_case, save_message
from app.graphs.qa_graph import run_qa, stream_qa
from app.services.data_catalog import build_data_catalog
from app.services.documents import persist_and_index
from app.services.guardrails import check_input


router = APIRouter()
logger = logging.getLogger(__name__)


def _sse(event: dict[str, Any]) -> str:
    """Encode one event as SSE so reverse proxies flush it immediately."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=50_000)


class ChatAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    data_base64: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=10)
    conversation_id: str | None = Field(default=None, max_length=64)
    case_id: str | None = Field(default=None, max_length=64)
    current_review: str = Field(default="", max_length=12000)
    response_mode: str = Field(default="chat", pattern="^(chat|review)$")
    data_catalog: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    screen_context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    metadata: dict[str, Any] = Field(default_factory=dict)


def _last_user_question(request: ChatRequest) -> str:
    message = next((item for item in reversed(request.messages) if item.role == "user"), None)
    if not message:
        raise HTTPException(status_code=422, detail="사용자 질문이 필요합니다.")
    return message.content


def _catalog_summary_for_prompt(case_id: str) -> dict[str, Any]:
    """Keep the default LLM context compact; detailed rows are retrieved only when requested."""
    catalog = build_data_catalog(case_id)
    items = [{
        "name": item.get("name"),
        "type": item.get("type"),
        "status": item.get("status"),
        "row_count": item.get("row_count"),
        "column_count": len(item.get("columns") or []),
        "knowledge_scope": item.get("knowledge_scope"),
    } for item in catalog["items"]]
    return {"count": len(items), "items": items, "refreshed_at": catalog["refreshed_at"]}


async def _prepare_request(request: ChatRequest) -> tuple[str, str, str, str]:
    question = _last_user_question(request)
    case_id = request.case_id or ensure_default_case()
    conversation_id = ensure_conversation(request.conversation_id, case_id)
    save_message(conversation_id, "user", question)
    attachment_context = await _process_attachments(conversation_id, case_id, request.attachments)
    context_blocks: list[str] = []
    recent_messages = request.messages[:-1][-8:]
    if recent_messages:
        recent_context = "\n".join(
            f"{'사용자' if item.role == 'user' else 'AI'}: {item.content}"
            for item in recent_messages
        )
        context_blocks.append(f"[최근 대화]\n{recent_context}")
    if request.current_review.strip():
        context_blocks.append(f"[현재 화면의 심사의견]\n{request.current_review.strip()}")
    if request.screen_context:
        context_blocks.append(
            "[현재 화면 상태]\n" + json.dumps(request.screen_context, ensure_ascii=False, default=str)
        )
    context_blocks.append(
        "[현재 입수 데이터 카탈로그 요약]\n"
        + json.dumps(_catalog_summary_for_prompt(case_id), ensure_ascii=False, default=str)
    )
    if attachment_context:
        context_blocks.append(attachment_context)
    # Keep the screen and catalog state available on every turn without exceeding the model context.
    return conversation_id, case_id, question, "\n\n".join(context_blocks)[:12_000]


async def _answer(request: ChatRequest) -> tuple[str, str, dict[str, Any]]:
    conversation_id, case_id, question, attachment_context = await _prepare_request(request)
    guardrail = check_input(question)
    if not guardrail.allowed:
        answer = guardrail.response or "해당 요청에는 답변할 수 없습니다."
        metadata = {"guardrail": guardrail.category, "agent": "guardrail"}
        save_message(conversation_id, "assistant", answer, metadata)
        return conversation_id, answer, metadata

    try:
        result = await run_qa(question, attachment_context, case_id, conversation_id, response_mode=request.response_mode)
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text[:2_000]
        logger.exception("Colab LLM HTTP error %s: %s", exc.response.status_code, response_text)
        if exc.response.status_code == 400 and "context" in response_text.lower():
            detail = "첨부 문서의 내용이 너무 길어 분석 범위를 초과했습니다. 문서를 나누거나 질문 범위를 좁혀 주세요."
        else:
            detail = "Colab LLM이 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."
        raise HTTPException(status_code=502, detail=detail) from exc
    except (httpx.RequestError, KeyError, TypeError, ValueError) as exc:
        logger.exception("Chat pipeline error")
        raise HTTPException(status_code=503, detail="Colab LLM 또는 RAG 서비스에 연결할 수 없습니다.") from exc

    answer = result.get("final_answer", "")
    metadata = {
        "agent": "generator_a_verified" if result.get("approved", True) else "validator_b",
        "validator_approved": result.get("approved", True),
        "validator_issues": result.get("validation_issues", []),
        "sql": result.get("sql_used", ""),
        "sources": result.get("sources", []),
        "workflow_status": result.get("workflow_status", "approved"),
        "human_review_required": result.get("workflow_status") == "needs_human_review",
        "human_review_reason": result.get("human_review_reason", ""),
        "revision_count": result.get("revision_count", 0),
        "retrieval_count": result.get("retrieval_count", 0),
        "issue_types": result.get("issue_types", []),
        "intent_brief": result.get("intent_brief", {}),
    }
    save_message(conversation_id, "assistant", answer, metadata)
    return conversation_id, answer, metadata


@router.post("/completions", response_model=ChatResponse)
async def create_chat_completion(request: ChatRequest) -> ChatResponse:
    conversation_id, answer, metadata = await _answer(request)
    return ChatResponse(
        conversation_id=conversation_id,
        message=ChatMessage(role="assistant", content=answer),
        metadata=metadata,
    )


@router.post("/completions/stream")
async def create_streaming_chat_completion(request: ChatRequest) -> StreamingResponse:
    async def generate():
        try:
            conversation_id, case_id, question, attachment_context = await _prepare_request(request)
            yield _sse({"type": "meta", "conversation_id": conversation_id})
            guardrail = check_input(question)
            if not guardrail.allowed:
                answer = guardrail.response or "해당 요청에는 답변할 수 없습니다."
                metadata = {"guardrail": guardrail.category, "agent": "guardrail"}
                save_message(conversation_id, "assistant", answer, metadata)
                yield _sse({"type": "token", "content": answer})
                yield _sse({"type": "done", "message": answer, "metadata": metadata})
                return
            async for event in stream_qa(
                question, attachment_context, case_id, conversation_id,
                response_mode=request.response_mode,
            ):
                if event["type"] != "done":
                    yield _sse(event)
                    continue
                result = event["result"]
                answer = result.get("final_answer", "")
                metadata = {"agent": "generator_a_verified" if result.get("approved", True) else "validator_b", "validator_approved": result.get("approved", True), "validator_issues": result.get("validation_issues", []), "issue_types": result.get("issue_types", []), "sql": result.get("sql_used", ""), "sources": result.get("sources", []), "workflow_status": result.get("workflow_status", "approved"), "human_review_required": result.get("workflow_status") == "needs_human_review", "human_review_reason": result.get("human_review_reason", ""), "revision_count": result.get("revision_count", 0), "retrieval_count": result.get("retrieval_count", 0), "intent_brief": result.get("intent_brief", {})}
                save_message(conversation_id, "assistant", answer, metadata)
                yield _sse({"type": "done", "message": answer, "metadata": metadata})
        except Exception as exc:
            logger.exception("Streaming chat pipeline error")
            detail = "Colab LLM이 요청을 처리하지 못했습니다." if isinstance(exc, httpx.HTTPStatusError) else "Colab LLM 또는 RAG 서비스에 연결할 수 없습니다."
            yield _sse({"type": "error", "detail": detail})
    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


async def _process_attachments(conversation_id: str, case_id: str, attachments: list[ChatAttachment]) -> str:
    image_count = sum(item.mime_type.startswith("image/") for item in attachments)
    if image_count > settings.MAX_IMAGES_PER_MESSAGE:
        raise HTTPException(
            status_code=422,
            detail=f"한 번에 이미지는 최대 {settings.MAX_IMAGES_PER_MESSAGE}개까지 분석할 수 있습니다.",
        )

    extracted: list[str] = []
    for attachment in attachments:
        raw = _decode_attachment(attachment)
        if attachment.mime_type.startswith("image/"):
            image_text = await _analyze_image(attachment, raw)
            stored, _, file_id = persist_and_index(
                conversation_id, attachment.filename, attachment.mime_type, raw, case_id
            )
            # Images have no local text extractor, so persist their model description separately.
            from app.database.poc_store import index_document

            index_document(file_id, attachment.filename, stored, attachment.mime_type, image_text, case_id=case_id)
            extracted.append(f"[첨부 이미지 {attachment.filename}]\n{image_text}")
        else:
            try:
                _, text, _ = persist_and_index(
                    conversation_id, attachment.filename, attachment.mime_type, raw, case_id
                )
            except ValueError as exc:
                raise HTTPException(status_code=415, detail=str(exc)) from exc
            extracted.append(f"[첨부 문서 {attachment.filename}]\n{text}")
    return "\n\n".join(extracted)[: settings.MAX_DOCUMENT_TEXT_CHARS]


async def _analyze_image(attachment: ChatAttachment, raw: bytes) -> str:
    content = [
        {
            "type": "text",
            "text": "이 이미지를 여신심사 관점에서 정확히 판독하세요. 보이는 문자, 표, 수치와 위험징후를 구조적으로 설명하세요.",
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{attachment.mime_type};base64,{base64.b64encode(raw).decode('ascii')}"
            },
        },
    ]
    return await ColabLLMClient().complete([{"role": "user", "content": content}], max_tokens=900)


def _decode_attachment(attachment: ChatAttachment) -> bytes:
    try:
        raw = base64.b64decode(attachment.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"잘못된 첨부파일입니다: {attachment.filename}") from exc
    if len(raw) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"{attachment.filename}: 최대 {settings.MAX_UPLOAD_SIZE_MB}MB까지 업로드할 수 있습니다.",
        )
    return raw
