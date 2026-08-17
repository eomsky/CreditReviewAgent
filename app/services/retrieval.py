"""Case-filtered retrieval and evidence normalization."""

from __future__ import annotations

import hashlib
import re

from app.core.config import settings
from app.domain.evidence import Evidence, EvidenceConflict, EvidenceSourceType, ValueType
from app.repositories.document_repository import DocumentRepository
from app.rag.retrievers.hybrid import HybridRetriever
from app.services.query import FinancialQueryService


class RetrievalService:
    def __init__(self, documents: DocumentRepository | None = None, query: FinancialQueryService | None = None, hybrid: HybridRetriever | None = None) -> None:
        self.documents = documents or DocumentRepository()
        self.query = query or FinancialQueryService()
        self.hybrid = hybrid or HybridRetriever(self.documents)

    def retrieve(self, question: str, *, case_id: str, extra_queries: list[str] | None = None) -> tuple[list[Evidence], str]:
        queries = [question, *(extra_queries or [])]
        evidence: list[Evidence] = []
        query_result = self.query.execute(question)
        query_id = ""
        if query_result:
            query_id = query_result.query_id
            for index, row in enumerate(query_result.rows):
                content = ", ".join(f"{key}={value}" for key, value in row.items())
                evidence.append(Evidence(
                    evidence_id=f"db:{query_id}:{index}", source_type=EvidenceSourceType.STRUCTURED_DB,
                    source_id=query_id, case_id=case_id, title="정형 DB 조회", content=content,
                    period=str(row.get("fiscal_year")) if row.get("fiscal_year") else None,
                    value_type=ValueType.ACTUAL, confidence=1.0,
                ))
        seen: set[str] = set()
        for query in queries:
            for row in self.hybrid.search(query, case_id=case_id, limit=settings.RAG_TOP_K):
                chunk_key = hashlib.sha256(f"{row['document_id']}:{row['content']}".encode()).hexdigest()[:16]
                if chunk_key in seen:
                    continue
                seen.add(chunk_key)
                evidence.append(Evidence(
                    evidence_id=f"doc:{chunk_key}", source_type=EvidenceSourceType.CASE_DOCUMENT,
                    source_id=str(row["document_id"]), document_id=str(row["document_id"]), case_id=row.get("case_id"),
                    title=str(row["title"]), filename=str(row["title"]), chunk_id=chunk_key,
                    content=str(row["content"]), retrieval_score=float(row.get("score") or 0), confidence=0.8,
                ))
        return evidence, query_id

    @staticmethod
    def find_conflicts(evidence: list[Evidence]) -> list[EvidenceConflict]:
        groups: dict[tuple[str, str, str], list[Evidence]] = {}
        for item in evidence:
            if item.metric and item.period and item.value is not None:
                groups.setdefault((item.metric, item.period, item.value_type), []).append(item)
        conflicts = []
        for key, items in groups.items():
            values = {str(item.value) for item in items}
            if len(values) > 1:
                conflicts.append(EvidenceConflict("/".join(key), [item.evidence_id for item in items], list(values), "동일 기준의 근거 값이 일치하지 않습니다."))
        return conflicts
