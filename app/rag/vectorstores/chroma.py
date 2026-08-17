"""Persistent Chroma vector store keyed by document/chunk IDs."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.rag.embeddings.hashing import HashingEmbedding


class ChromaVectorStore:
    def __init__(self, embedding: HashingEmbedding | None = None) -> None:
        self.embedding = embedding or HashingEmbedding()
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            import chromadb
            client = chromadb.PersistentClient(path=str(settings.CHROMA_PERSIST_DIR))
            self._collection = client.get_or_create_collection(settings.CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"})
        return self._collection

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        if ids:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=self.embedding.embed(documents))

    def delete_document(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})

    def search(self, query: str, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        result = self.collection.query(query_embeddings=self.embedding.embed([query]), n_results=max(limit * 4, limit))
        rows = []
        for item_id, document, metadata, distance in zip(
            result.get("ids", [[]])[0], result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0], result.get("distances", [[]])[0], strict=False,
        ):
            if metadata.get("knowledge_scope") != "common" and metadata.get("case_id") != case_id:
                continue
            rows.append({"chunk_id": item_id, "document_id": metadata["document_id"], "title": metadata["title"], "content": document, "case_id": metadata.get("case_id"), "knowledge_scope": metadata.get("knowledge_scope", "case"), "score": 1.0 - float(distance), "retrieval_method": "vector"})
            if len(rows) >= limit:
                break
        return rows
