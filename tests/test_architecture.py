import asyncio
from pathlib import Path

import httpx
import pytest

from app.clients.colab_llm import ColabLLMClient, LLMProtocolError
from app.core.config import settings
from app.database.poc_store import connect, create_case, delete_case_document, index_document, initialize_database, search_documents
from app.domain.evidence import Evidence, EvidenceSourceType, ValueType
from app.services.authorization import AuthorizationError, AuthorizationService
from app.services.query import FinancialQueryService
from app.services.retrieval import RetrievalService
from app.database.poc_store import TextToSQLService
from app.rag.evaluation import evaluate_rankings


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", tmp_path / "chroma")
    initialize_database(seed=True)
    return tmp_path


def test_predefined_query_is_bounded(isolated):
    result = FinancialQueryService().execute("고위험 기업을 알려줘")
    assert result and result.query_id == "predefined:high_risk"
    assert len(result.rows) <= settings.SQL_MAX_ROWS


def test_sql_guard_blocks_write_and_unknown_table():
    with pytest.raises(ValueError):
        TextToSQLService._validate("DELETE FROM companies")
    with pytest.raises(ValueError):
        TextToSQLService._validate("SELECT * FROM auth_users")


def test_authorization_precedes_case_access(isolated):
    case = create_case("테스트", "A기업")
    AuthorizationService().require_case("poc-user", case["id"])
    with pytest.raises(AuthorizationError):
        AuthorizationService().require_case("other-user", case["id"])


def test_deleted_document_is_not_retrievable(isolated):
    case = create_case("문서", "A기업")
    path = isolated / "policy.txt"
    path.write_text("DSCR 1.5배 이상", encoding="utf-8")
    with connect() as connection:
        connection.execute("INSERT INTO conversations VALUES ('conv',?,?,?)", (case["id"], "now", "now"))
        connection.execute("INSERT INTO uploaded_files(id,conversation_id,original_name,stored_path,mime_type,size_bytes,extracted_text,created_at,case_id,status,error_message) VALUES ('doc','conv','policy.txt',?,'text/plain',10,'DSCR 1.5배 이상','now',?,'READY','')", (str(path), case["id"]))
    index_document("doc", "정책", path, "text/plain", "DSCR 1.5배 이상", case_id=case["id"])
    assert search_documents("DSCR", case_id=case["id"])
    delete_case_document(case["id"], "doc")
    assert not search_documents("DSCR", case_id=case["id"])


def test_actual_and_forecast_are_not_conflicts():
    actual = Evidence("a", EvidenceSourceType.STRUCTURED_DB, "db", "c", "actual", "", period="2025", value_type=ValueType.ACTUAL, metric="revenue", value=100)
    forecast = Evidence("f", EvidenceSourceType.CASE_DOCUMENT, "doc", "c", "forecast", "", period="2025", value_type=ValueType.FORECAST, metric="revenue", value=120)
    assert RetrievalService.find_conflicts([actual, forecast]) == []
    other = Evidence("b", EvidenceSourceType.CASE_DOCUMENT, "doc2", "c", "other", "", period="2025", value_type=ValueType.ACTUAL, metric="revenue", value=110)
    assert RetrievalService.find_conflicts([actual, other])


def test_llm_malformed_response_is_rejected(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(LLMProtocolError):
        asyncio.run(ColabLLMClient(transport).complete([{"role": "user", "content": "x"}]))


def test_llm_retries_500(monkeypatch):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(500) if calls == 1 else httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr(settings, "COLAB_LLM_RETRY_BACKOFF_SECONDS", 0)
    assert asyncio.run(ColabLLMClient(httpx.MockTransport(handler)).complete([])) == "ok"
    assert calls == 2


def test_retrieval_metrics_are_generation_independent():
    metrics = evaluate_rankings([["a", "b"], ["x", "c"]], [{"b"}, {"z"}], 2)
    assert metrics.hit_at_k == 0.5
    assert metrics.recall_at_k == 0.5
    assert metrics.mrr == 0.25
