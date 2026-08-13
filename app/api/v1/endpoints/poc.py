"""POC observability endpoints for seeded data and stored interactions."""

from fastapi import APIRouter

from app.database.poc_store import connect


router = APIRouter()


@router.get("/stats")
async def poc_stats() -> dict[str, int]:
    tables = ("companies", "financials", "loans", "documents", "document_chunks", "conversations", "messages", "uploaded_files")
    with connect() as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
