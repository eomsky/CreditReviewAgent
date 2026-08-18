from pathlib import Path

import pytest

from app.core.config import settings
from app.database.poc_store import (
    TextToSQLService,
    connect,
    index_document,
    initialize_database,
    search_documents,
)


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'poc.db'}")
    initialize_database(seed=True)
    return tmp_path


def test_seed_contains_sufficient_structured_data(isolated_db: Path):
    with connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 150
        assert connection.execute("SELECT COUNT(*) FROM financials").fetchone()[0] >= 600
        assert connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0] >= 150
        assert connection.execute("SELECT COUNT(*) FROM customer_portfolio").fetchone()[0] >= 3
        assert connection.execute("SELECT COUNT(*) FROM collateral").fetchone()[0] >= 2
        assert connection.execute("SELECT COUNT(*) FROM credit_assessments").fetchone()[0] >= 1
        assert connection.execute("SELECT COUNT(*) FROM business_plans").fetchone()[0] >= 1
        target = connection.execute("SELECT * FROM companies WHERE name='A기업'").fetchone()
        assert target["industry"] == "자동차 및 전기차 부품 제조"


def test_text_to_sql_is_read_only_and_returns_high_risk_companies(isolated_db: Path):
    result = TextToSQLService().execute("고위험 기업을 부채비율 높은 순으로 알려줘")
    assert result is not None
    assert result.sql.lower().startswith("select")
    assert result.rows
    assert result.rows[0]["risk_level"] == "고위험"


def test_fts_rag_returns_indexed_credit_policy(isolated_db: Path, tmp_path: Path):
    path = tmp_path / "policy.txt"
    path.write_text("부채비율 250% 이상은 고위험 검토 대상으로 분류한다.", encoding="utf-8")
    index_document("policy", "여신정책", path, "text/plain", path.read_text(encoding="utf-8"))
    results = search_documents("부채비율 고위험 기준")
    assert results
    assert results[0]["title"] == "여신정책"
