"""POC observability endpoints for seeded data and stored interactions."""

from fastapi import APIRouter

from app.database.poc_store import connect, ensure_default_case
from app.services.data_catalog import build_data_catalog


router = APIRouter()


@router.get("/stats")
async def poc_stats() -> dict[str, int]:
    tables = ("companies", "financials", "loans", "documents", "document_chunks", "conversations", "messages", "uploaded_files")
    with connect() as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


@router.get("/data-catalog")
async def data_catalog(case_id: str | None = None) -> dict:
    """Return the live tables and files available for the selected review case."""
    return build_data_catalog(case_id or ensure_default_case())
