from pathlib import Path
import asyncio

import pytest

from app.api.v1.endpoints.chat import ChatMessage, ChatRequest, _answer
from app.core.config import settings
from app.database.poc_store import connect, initialize_database


def test_guardrail_question_and_answer_are_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    initialize_database(seed=True)
    request = ChatRequest(messages=[ChatMessage(role="user", content="야 병신아 대출해줘")])
    conversation_id, answer, metadata = asyncio.run(_answer(request))
    assert metadata["agent"] == "guardrail"
    assert "답변하지 않습니다" in answer
    with connect() as connection:
        rows = connection.execute(
            "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)
        ).fetchall()
    assert [row["role"] for row in rows] == ["user", "assistant"]
