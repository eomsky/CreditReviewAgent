"""Authorization trust boundary applied before case data retrieval."""

from __future__ import annotations

from app.database.poc_store import connect


class AuthorizationError(PermissionError):
    pass


class AuthorizationService:
    def require_case(self, principal_id: str, case_id: str) -> None:
        if not principal_id or not case_id:
            raise AuthorizationError("principal and case are required")
        with connect() as connection:
            allowed = connection.execute(
                "SELECT 1 FROM case_access WHERE principal_id=? AND case_id=?", (principal_id, case_id)
            ).fetchone()
        if not allowed:
            raise AuthorizationError("해당 심사건에 접근할 권한이 없습니다.")

    def require_document(self, principal_id: str, case_id: str, document_id: str) -> None:
        self.require_case(principal_id, case_id)
        with connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM uploaded_files WHERE id=? AND case_id=?", (document_id, case_id)
            ).fetchone()
        if not exists:
            raise AuthorizationError("해당 문서에 접근할 권한이 없습니다.")
