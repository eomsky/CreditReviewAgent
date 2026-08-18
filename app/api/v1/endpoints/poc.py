"""POC observability endpoints for seeded data and stored interactions."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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


@router.get("/files/{file_id}")
async def source_file(file_id: str, case_id: str | None = None) -> FileResponse:
    """Stream an authorized original upload inline for the read-only source viewer."""
    selected_case = case_id or ensure_default_case()
    with connect() as connection:
        row = connection.execute(
            """SELECT d.title original_name,d.source_path stored_path,d.mime_type
            FROM documents d
            WHERE d.id=? AND (d.knowledge_scope='common' OR d.case_id=?)
            UNION ALL
            SELECT uf.original_name,uf.stored_path,uf.mime_type
            FROM uploaded_files uf WHERE uf.id=? AND uf.case_id=?
            LIMIT 1""",
            (file_id, selected_case, file_id, selected_case),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="원본 파일을 찾을 수 없습니다.")
    stored = Path(row["stored_path"]).resolve()
    if not stored.is_file():
        raise HTTPException(status_code=404, detail="저장된 원본 파일이 없습니다.")
    return FileResponse(
        stored,
        media_type=row["mime_type"] or "application/octet-stream",
        filename=row["original_name"],
        content_disposition_type="inline",
    )
