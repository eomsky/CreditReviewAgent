from pathlib import Path
import asyncio

import pytest

from app.api.v1.endpoints.chat import ChatMessage, ChatRequest, _answer, _catalog_summary_for_prompt, _prepare_request, _sse
from app.core.config import settings
from app.database.poc_store import connect, initialize_database


def test_sse_encoder_creates_flushable_event_frame():
    frame = _sse({"type": "token", "content": "첫 토큰"})
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert '"content": "첫 토큰"' in frame


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


def test_screen_and_server_catalog_are_included_in_agent_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}")
    initialize_database(seed=True)
    request = ChatRequest(
        messages=[ChatMessage(role="user", content="현재 입수 자료를 알려줘")],
        current_review="## 종합 심사의견\n검토 중",
        data_catalog=[{"name": "재무제표원장", "type": "테이블", "row_count": 2}],
        screen_context={"input_data_count": 12, "selected_source": {"name": "재무제표원장"}},
    )
    _, _, _, context = asyncio.run(_prepare_request(request))
    assert "[현재 화면 상태]" in context
    assert '"input_data_count": 12' in context
    assert "[현재 입수 데이터 카탈로그 요약]" in context
    assert '"companies"' in context
    assert '"sample_rows"' not in context
    assert '"rows"' not in context
    assert '"columns"' not in context


def test_recent_conversation_is_available_to_intent_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'history.db'}")
    initialize_database(seed=True)
    request = ChatRequest(messages=[
        ChatMessage(role="user", content="재무자료와 대출자료를 비교해줘"),
        ChatMessage(role="assistant", content="두 자료를 비교했습니다."),
        ChatMessage(role="user", content="그중 두 번째 자료의 행 수는?"),
    ])
    _, _, question, context = asyncio.run(_prepare_request(request))
    assert question == "그중 두 번째 자료의 행 수는?"
    assert "[최근 대화]" in context
    assert "재무자료와 대출자료를 비교해줘" in context
    assert "두 자료를 비교했습니다." in context


def test_catalog_prompt_is_compact_and_not_duplicated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'compact.db'}")
    initialize_database(seed=True)
    from app.database.poc_store import ensure_default_case

    summary = _catalog_summary_for_prompt(ensure_default_case())
    assert summary["count"] == len(summary["items"])
    assert {item["name"] for item in summary["items"] if item["type"] == "테이블"} == {
        "companies", "financials", "loans"
    }
    assert all("rows" not in item and "columns" not in item and "body" not in item for item in summary["items"])
    assert all("column_count" in item for item in summary["items"])
    assert all("key_columns" in item for item in summary["items"])
    assert all("refreshed_at" not in item for item in summary["items"])
    table_items = [item for item in summary["items"] if item["type"] == "테이블"]
    assert all("id" not in item["key_columns"] and "created_at" not in item["key_columns"] for item in table_items)
