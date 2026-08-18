from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import settings
from app.database.poc_store import connect, ensure_default_case, initialize_database
from app.services.data_catalog import build_data_catalog


def test_catalog_tracks_live_tables_and_document_additions_and_removals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}")
    initialize_database(seed=True)
    case_id = ensure_default_case()

    initial = build_data_catalog(case_id)
    tables = {item["name"]: item for item in initial["items"] if item["type"] == "테이블"}
    assert set(tables) == {
        "business_plans", "collateral", "companies", "credit_applications",
        "credit_assessments", "customer_portfolio", "financials", "loans",
    }
    assert tables["companies"]["row_count"] == 181
    assert initial["count"] == len(initial["items"])

    document_id = "dynamic-catalog-document"
    with connect() as connection:
        connection.execute(
            """INSERT INTO documents
            (id,case_id,knowledge_scope,title,source_path,mime_type,created_at,status,version)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                document_id,
                case_id,
                "case",
                "추가 심사자료.pdf",
                "data/uploads/extra.pdf",
                "application/pdf",
                datetime.now(UTC).isoformat(),
                "READY",
                1,
            ),
        )
        connection.execute(
            "INSERT INTO document_chunks(document_id,title,content,source_path) VALUES (?,?,?,?)",
            (document_id, "추가 심사자료.pdf", "추가된 심사자료 내용", "data/uploads/extra.pdf"),
        )

    increased = build_data_catalog(case_id)
    assert increased["count"] == initial["count"] + 1
    document = next(item for item in increased["items"] if item["name"] == "추가 심사자료.pdf")
    assert document["source_url"] == f"/api/v1/poc/files/{document_id}?case_id={case_id}"

    with connect() as connection:
        connection.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id=?", (document_id,))

    decreased = build_data_catalog(case_id)
    assert decreased["count"] == initial["count"]
    assert all(item["name"] != "추가 심사자료.pdf" for item in decreased["items"])
