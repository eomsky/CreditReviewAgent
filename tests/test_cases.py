from pathlib import Path

import pytest

from app.core.config import settings
from app.database.poc_store import (
    create_case,
    ensure_conversation,
    get_case,
    initialize_database,
    list_agent_events,
    list_cases,
    record_agent_event,
    update_case_status,
)


def test_case_lifecycle_and_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cases.db'}")
    initialize_database(seed=False)
    item = create_case("A기업 / 신규 여신", "A기업", "신규 여신", "김심사")
    assert get_case(item["id"])["status"] == "IN_PROGRESS"
    assert list_cases(query="A기업")[0]["id"] == item["id"]

    conversation_id = ensure_conversation(case_id=item["id"])
    record_agent_event(item["id"], conversation_id, "generator", "generator.draft_created", "초안")
    events = list_agent_events(item["id"], conversation_id)
    assert events[0]["event_type"] == "generator.draft_created"

    completed = update_case_status(item["id"], "COMPLETED")
    assert completed["status"] == "COMPLETED"
    assert completed["completed_at"]