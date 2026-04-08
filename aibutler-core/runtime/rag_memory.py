#!/usr/bin/env python3
"""
aiButler RAG Memory — local vector store for contextual recall.

Uses ChromaDB with the default embedding function (sentence-transformers).
All data stays local in ~/.aibutler/rag/.

Install:
  pip install chromadb

Usage:
  from runtime.rag_memory import RAGMemory
  rag = RAGMemory()
  rag.add("User prefers short responses", {"source": "feedback", "session": "abc"})
  results = rag.query("How does the user like responses?")
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


RAG_DIR = Path.home() / ".aibutler" / "rag"


class RAGMemory:
    def __init__(self, path: str | Path = RAG_DIR):
        self.path = Path(path).expanduser()
        self.path.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None

    def _init(self):
        """Lazy-init ChromaDB (only when actually used)."""
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            self._client = chromadb.PersistentClient(path=str(self.path))
            self._collection = self._client.get_or_create_collection(
                name="butler_memory",
                embedding_function=embedding_functions.DefaultEmbeddingFunction(),
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            raise RuntimeError(
                "ChromaDB not installed. Run: pip install chromadb"
            )

    def add(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """Add a memory entry. Returns the assigned ID."""
        self._init()
        doc_id = str(abs(hash(content + str(metadata))))
        self._collection.upsert(
            documents=[content],
            metadatas=[metadata or {}],
            ids=[doc_id],
        )
        return doc_id

    def add_bulk(self, entries: list[tuple[str, dict]]) -> list[str]:
        """Add multiple entries at once. Each entry is (content, metadata)."""
        self._init()
        ids, docs, metas = [], [], []
        for content, metadata in entries:
            doc_id = str(abs(hash(content + str(metadata))))
            ids.append(doc_id)
            docs.append(content)
            metas.append(metadata or {})
        self._collection.upsert(documents=docs, metadatas=metas, ids=ids)
        return ids

    def query(self, query: str, n: int = 5, where: dict | None = None) -> list[dict]:
        """Semantic search. Returns list of {content, metadata, distance}."""
        self._init()
        kwargs: dict[str, Any] = {"query_texts": [query], "n_results": min(n, self._collection.count())}
        if where:
            kwargs["where"] = where
        if kwargs["n_results"] == 0:
            return []
        results = self._collection.query(**kwargs)
        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({"content": doc, "metadata": meta, "distance": dist})
        return output

    def delete(self, doc_id: str) -> None:
        """Delete a memory entry by ID."""
        self._init()
        self._collection.delete(ids=[doc_id])

    def count(self) -> int:
        """Return total number of stored memories."""
        self._init()
        return self._collection.count()

    def clear(self) -> None:
        """Wipe all memories (irreversible)."""
        self._init()
        self._client.delete_collection("butler_memory")
        self._collection = None
        self._client = None
