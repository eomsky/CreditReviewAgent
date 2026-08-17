"""Vector indexing connected to the document ingestion lifecycle."""

from __future__ import annotations

from app.database.poc_store import _chunk_text
from app.rag.vectorstores.chroma import ChromaVectorStore


class VectorIndexer:
    def __init__(self, store: ChromaVectorStore | None = None) -> None:
        self.store = store or ChromaVectorStore()

    def index(self, document_id: str, title: str, text: str, case_id: str | None, knowledge_scope: str = "case") -> int:
        chunks = _chunk_text(text)
        ids = [f"{document_id}:{index}" for index in range(len(chunks))]
        metadata = [{"document_id": document_id, "case_id": case_id or "", "title": title, "chunk_index": index, "knowledge_scope": knowledge_scope, "version": 1} for index in range(len(chunks))]
        self.store.delete_document(document_id)
        self.store.upsert(ids, chunks, metadata)
        return len(chunks)

    def delete(self, document_id: str) -> None:
        self.store.delete_document(document_id)
