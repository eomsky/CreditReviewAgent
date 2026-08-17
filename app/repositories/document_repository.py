"""Document metadata and lexical retrieval repository."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.poc_store import delete_case_document, list_case_documents, search_documents
from app.services.authorization import AuthorizationService


class DocumentRepository:
    def __init__(self, authorization: AuthorizationService | None = None, principal_id: str = "poc-user") -> None:
        self.authorization = authorization or AuthorizationService()
        self.principal_id = principal_id

    def search(self, query: str, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        if not case_id:
            return []
        self.authorization.require_case(self.principal_id, case_id)
        return search_documents(query, limit=limit, case_id=case_id)

    def list_for_case(self, case_id: str) -> list[dict[str, Any]]:
        return list_case_documents(case_id)

    def delete(self, case_id: str, document_id: str) -> Path | None:
        self.authorization.require_document(self.principal_id, case_id, document_id)
        return delete_case_document(case_id, document_id)
