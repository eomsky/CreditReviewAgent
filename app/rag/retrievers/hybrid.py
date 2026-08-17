"""Reciprocal-rank fusion of lexical and semantic retrieval."""

from __future__ import annotations

from typing import Any

from app.rag.vectorstores.chroma import ChromaVectorStore
from app.repositories.document_repository import DocumentRepository


class HybridRetriever:
    def __init__(self, lexical: DocumentRepository | None = None, vector: ChromaVectorStore | None = None) -> None:
        self.lexical = lexical or DocumentRepository()
        self.vector = vector or ChromaVectorStore()

    def search(self, query: str, *, case_id: str, limit: int, mode: str = "hybrid") -> list[dict[str, Any]]:
        lexical = self.lexical.search(query, case_id=case_id, limit=limit) if mode in {"bm25", "hybrid"} else []
        try:
            semantic = self.vector.search(query, case_id=case_id, limit=limit) if mode in {"vector", "hybrid"} else []
        except Exception:
            semantic = []
        if mode == "bm25":
            return lexical
        if mode == "vector":
            return semantic
        fused: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}
        for results in (lexical, semantic):
            for rank, item in enumerate(results, start=1):
                key = str(item.get("chunk_id") or f"{item['document_id']}:{hash(item['content'])}")
                fused[key] = item
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
        return [{**fused[key], "fusion_score": score, "retrieval_method": "hybrid"} for key, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]]
