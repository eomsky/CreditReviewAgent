"""Case-scoped document upload, listing, deletion, and trace endpoints."""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.database.poc_store import (
    delete_case_document,
    ensure_conversation,
    get_case,
    list_agent_events,
    list_case_documents,
)
from app.services.documents import persist_and_index

router = APIRouter()


@router.get("/cases/{case_id}/documents")
def get_documents(case_id: str):
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="심사건을 찾을 수 없습니다.")
    return {"items": list_case_documents(case_id)}


@router.post("/cases/{case_id}/documents", status_code=201)
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
):
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="심사건을 찾을 수 없습니다.")
    raw = await file.read()
    if len(raw) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기 제한을 초과했습니다.")
    conversation_id = ensure_conversation(conversation_id, case_id)
    try:
        _, text, document_id = persist_and_index(
            conversation_id, file.filename or "document", file.content_type or "application/octet-stream", raw, case_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": document_id, "status": "READY", "text_length": len(text)}


@router.delete("/cases/{case_id}/documents/{document_id}", status_code=204)
def delete_document(case_id: str, document_id: str):
    path = delete_case_document(case_id, document_id)
    if path is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    Path(path).unlink(missing_ok=True)


@router.get("/cases/{case_id}/events/stream")
def stream_events(case_id: str, conversation_id: str | None = None):
    async def generate():
        cursor = 0
        while True:
            events = list_agent_events(case_id, conversation_id)
            for event in events:
                if event["id"] > cursor:
                    cursor = event["id"]
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.75)

    return StreamingResponse(generate(), media_type="text/event-stream")
@router.get("/cases/{case_id}/events")
def get_events(case_id: str, conversation_id: str | None = None):
    return {"items": list_agent_events(case_id, conversation_id)}