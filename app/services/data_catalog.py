"""Dynamic catalog of database tables and files available to the review agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.database.poc_store import ALLOWED_QUERY_TABLES, connect


def _file_type(mime_type: str, name: str) -> str:
    mime = (mime_type or "").lower()
    suffix = name.rsplit(".", 1)[-1].upper() if "." in name else "파일"
    if mime.startswith("image/"):
        return "이미지"
    return {
        "application/pdf": "PDF",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
        "text/plain": "TXT",
        "text/csv": "CSV",
    }.get(mime, suffix)


def build_data_catalog(case_id: str) -> dict[str, Any]:
    """Build the single source of truth used by both the UI and the agent."""
    items: list[dict[str, Any]] = []
    with connect() as connection:
        for table in sorted(ALLOWED_QUERY_TABLES):
            columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            sample = connection.execute(f"SELECT * FROM {table} LIMIT 5").fetchall()
            items.append({
                "name": table,
                "type": "테이블",
                "status": "조회 가능",
                "columns": columns,
                "rows": [[row[column] for column in columns] for row in sample],
                "row_count": count,
                "source_key": f"table:{table}",
            })

        documents = connection.execute(
            """SELECT d.id,d.title,d.mime_type,d.status,d.knowledge_scope,d.created_at,
            (SELECT COUNT(*) FROM document_chunks ch WHERE ch.document_id=d.id) chunk_count,
            (SELECT content FROM document_chunks ch WHERE ch.document_id=d.id LIMIT 1) summary
            FROM documents d
            WHERE d.knowledge_scope='common' OR d.case_id=?
            ORDER BY d.created_at DESC""",
            (case_id,),
        ).fetchall()
        for row in documents:
            items.append({
                "name": row["title"],
                "type": _file_type(row["mime_type"], row["title"]),
                "status": "색인 완료" if row["status"] == "READY" else row["status"],
                "body": (row["summary"] or "")[:1_200],
                "row_count": row["chunk_count"],
                "source_key": f"document:{row['id']}",
                "source_url": f"/api/v1/poc/files/{row['id']}?case_id={case_id}",
                "knowledge_scope": row["knowledge_scope"],
                "created_at": row["created_at"],
            })

        pending_files = connection.execute(
            """SELECT uf.id,uf.original_name,uf.mime_type,uf.size_bytes,uf.status,
            uf.error_message,uf.created_at
            FROM uploaded_files uf
            WHERE uf.case_id=? AND NOT EXISTS (
                SELECT 1 FROM documents d WHERE d.id=uf.id
            )
            ORDER BY uf.created_at DESC""",
            (case_id,),
        ).fetchall()
        for row in pending_files:
            items.append({
                "name": row["original_name"],
                "type": _file_type(row["mime_type"], row["original_name"]),
                "status": "심사대상 기업 불일치" if row["status"] == "EXCLUDED" else row["status"],
                "body": row["error_message"] or "업로드 후 색인 처리 중인 자료입니다.",
                "size_bytes": row["size_bytes"],
                "source_key": f"upload:{row['id']}",
                "source_url": f"/api/v1/poc/files/{row['id']}?case_id={case_id}",
                "created_at": row["created_at"],
            })

    for index, item in enumerate(items, start=1):
        item["id"] = index
    return {
        "case_id": case_id,
        "count": len(items),
        "items": items,
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
