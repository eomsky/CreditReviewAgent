from pathlib import Path

import pytest

from app.core.config import settings
from app.database.poc_store import ensure_default_case, initialize_database
from app.services.initial_review import build_initial_review


def test_initial_review_is_grounded_in_rich_seed_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'initial.db'}")
    initialize_database(seed=True)
    result = build_initial_review(ensure_default_case())
    text = result["text"]
    assert "2025년 매출액은 1,680억원" in text
    assert "부채비율은 108.8%" in text
    assert "유동비율은 152.4%" in text
    assert "DSCR은 1.45배" in text
    assert "신청금액은 300억원" in text
    assert "수주잔고는 520억원" in text
    assert len(result["sources"]) == 8
