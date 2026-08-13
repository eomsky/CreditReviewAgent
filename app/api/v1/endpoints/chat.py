"""Grounded conversational endpoint with persistence, RAG, agents, and guardrails."""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.clients.colab_llm import ColabLLMClient
from app.core.config import settings
from app.database.poc_store import ensure_conversation, save_message
from app.graphs.qa_graph import run_qa
from app.services.documents import persist_and_index
from app.services.guardrails import check_input


router = APIRouter()


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


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    metadata: dict[str, Any] = Field(default_factory=dict)


def _last_user_question(request: ChatRequest) -> str:
    message = next((item for item in reversed(request.messages) if item.role == "user"), None)
    if not message:
        raise HTTPException(status_code=422, detail="사용자 질문이 필요합니다.")
    return message.content


async def _prepare_request(request: ChatRequest) -> tuple[str, str, str]:
    question = _last_user_question(request)
    conversation_id = ensure_conversation(request.conversation_id)
    save_message(conversation_id, "user", question)
    attachment_context = await _process_attachments(conversation_id, request.attachments)
    return conversation_id, question, attachment_context


async def _answer(request: ChatRequest) -> tuple[str, str, dict[str, Any]]:
    conversation_id, question, attachment_context = await _prepare_request(request)
    guardrail = check_input(question)
    if not guardrail.allowed:
        answer = guardrail.response or "해당 요청에는 답변할 수 없습니다."
        metadata = {"guardrail": guardrail.category, "agent": "guardrail"}
        save_message(conversation_id, "assistant", answer, metadata)
        return conversation_id, answer, metadata

    try:
        result = await run_qa(question, attachment_context)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Colab LLM이 요청을 거절했습니다.") from exc
    except (httpx.RequestError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Colab LLM 또는 RAG 서비스에 연결할 수 없습니다.") from exc

    answer = result.get("final_answer", "")
    metadata = {
        "agent": "validator_b" if not result.get("approved", True) else "generator_a_verified",
        "validator_approved": result.get("approved", True),
        "validator_issues": result.get("issues", []),
        "sql": result.get("sql_used", ""),
        "sources": result.get("sources", []),
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
    conversation_id, answer, metadata = await _answer(request)

    async def generate():
        for start in range(0, len(answer), 18):
            yield answer[start : start + 18]
            await asyncio.sleep(0)

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Conversation-ID": conversation_id,
            "X-Agent-Result": "verified" if metadata.get("validator_approved", True) else "revised",
        },
    )


async def _process_attachments(conversation_id: str, attachments: list[ChatAttachment]) -> str:
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
                conversation_id, attachment.filename, attachment.mime_type, raw
            )
            # Images have no local text extractor, so persist their model description separately.
            from app.database.poc_store import index_document

            index_document(file_id, attachment.filename, stored, attachment.mime_type, image_text)
            extracted.append(f"[첨부 이미지 {attachment.filename}]\n{image_text}")
        else:
            try:
                _, text, _ = persist_and_index(
                    conversation_id, attachment.filename, attachment.mime_type, raw
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
