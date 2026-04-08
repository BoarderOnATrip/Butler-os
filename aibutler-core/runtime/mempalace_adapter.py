#!/usr/bin/env python3
"""
Butler MemPalace adapter.

Keeps Butler's markdown-first context repo as the source of truth and projects
it into a MemPalace-compatible Chroma collection for long-horizon semantic
recall. This intentionally stays thin: canonical data lives in Butler, while
the index is a disposable recall layer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from runtime.context_repository import KIND_DIRECTORIES, parse_markdown_document
from runtime.models import ContextEvent, ContextPendingItem, ContextSheet

DEFAULT_MEMPALACE_DIR = Path.home() / ".aibutler" / "mempalace" / "palace"
DEFAULT_COLLECTION_NAME = "mempalace_drawers"


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "unknown"


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _json_text(value: Any) -> str:
    if value in ("", None, [], {}):
        return ""
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        return str(value)


def _compact_join(parts: list[str]) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


class ButlerMemPalaceIndex:
    """Thin adapter from Butler context repo -> MemPalace-style Chroma index."""

    def __init__(
        self,
        *,
        context_root: str | Path,
        palace_path: str | Path = DEFAULT_MEMPALACE_DIR,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ):
        self.context_root = Path(context_root).expanduser()
        self.palace_path = Path(palace_path).expanduser()
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _init(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError as exc:
            raise RuntimeError("ChromaDB is not installed. Run: pip install chromadb") from exc

        self.palace_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.palace_path))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=embedding_functions.DefaultEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        self._init()
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None
        self._client = None
        self._init()

    def count(self) -> int:
        self._init()
        return self._collection.count()

    def status(self) -> dict[str, Any]:
        self._init()
        count = self._collection.count()
        wings: dict[str, int] = {}
        rooms: dict[str, int] = {}
        if count:
            payload = self._collection.get(include=["metadatas"], limit=count)
            for metadata in payload.get("metadatas", []):
                wing = str((metadata or {}).get("wing") or "unknown")
                room = str((metadata or {}).get("room") or "unknown")
                wings[wing] = wings.get(wing, 0) + 1
                rooms[room] = rooms.get(room, 0) + 1

        return {
            "palace_path": str(self.palace_path),
            "collection_name": self.collection_name,
            "total_drawers": count,
            "wings": wings,
            "rooms": rooms,
            "context_root": str(self.context_root),
        }

    def query(self, query: str, *, limit: int = 5, wing: str | None = None, room: str | None = None) -> dict[str, Any]:
        self._init()
        if not query.strip():
            return {
                "query": query,
                "filters": {"wing": wing, "room": room},
                "results": [],
            }

        total = self._collection.count()
        if total == 0:
            return {
                "query": query,
                "filters": {"wing": wing, "room": room},
                "results": [],
            }

        where: dict[str, Any] = {}
        if wing and room:
            where = {"$and": [{"wing": wing}, {"room": room}]}
        elif wing:
            where = {"wing": wing}
        elif room:
            where = {"room": room}

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(max(limit, 1), total),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        result = self._collection.query(**kwargs)
        hits: list[dict[str, Any]] = []
        for document, metadata, distance in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            meta = metadata or {}
            hits.append(
                {
                    "text": document,
                    "ref": meta.get("ref"),
                    "title": meta.get("title"),
                    "wing": meta.get("wing", "unknown"),
                    "room": meta.get("room", "unknown"),
                    "kind": meta.get("kind", "unknown"),
                    "source_file": meta.get("source_file", ""),
                    "similarity": round(1 - float(distance), 3),
                    "created_at": meta.get("created_at"),
                    "updated_at": meta.get("updated_at"),
                }
            )

        return {
            "query": query,
            "filters": {"wing": wing, "room": room},
            "results": hits,
        }

    def index_context(
        self,
        *,
        include_sheets: bool = True,
        include_pending: bool = True,
        include_events: bool = True,
        clear: bool = False,
    ) -> dict[str, Any]:
        if clear:
            self.reset()
        else:
            self._init()

        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        counts = {"sheets": 0, "pending": 0, "events": 0}

        if include_sheets:
            for path in self._iter_sheet_paths():
                sheet = self._read_sheet(path)
                if not sheet:
                    continue
                doc, metadata, doc_id = self._sheet_document(sheet)
                documents.append(doc)
                metadatas.append(metadata)
                ids.append(doc_id)
                counts["sheets"] += 1

        if include_pending:
            for path in sorted(self.context_root.glob("pending/*/*.md")):
                pending = self._read_pending(path)
                if not pending:
                    continue
                doc, metadata, doc_id = self._pending_document(pending)
                documents.append(doc)
                metadatas.append(metadata)
                ids.append(doc_id)
                counts["pending"] += 1

        if include_events:
            for event in self._iter_events():
                doc, metadata, doc_id = self._event_document(event)
                documents.append(doc)
                metadatas.append(metadata)
                ids.append(doc_id)
                counts["events"] += 1

        if ids:
            self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        return {
            "palace_path": str(self.palace_path),
            "collection_name": self.collection_name,
            "indexed_documents": len(ids),
            "indexed_sheets": counts["sheets"],
            "indexed_pending": counts["pending"],
            "indexed_events": counts["events"],
            "total_drawers": self._collection.count(),
            "context_root": str(self.context_root),
        }

    def _iter_sheet_paths(self) -> list[Path]:
        paths: list[Path] = []
        for directory in sorted(set(KIND_DIRECTORIES.values())):
            paths.extend((self.context_root / directory).glob("*.md"))
        return sorted(paths)

    def _read_sheet(self, path: Path) -> ContextSheet | None:
        from runtime.context_repository import ContextRepository

        repo = ContextRepository(self.context_root)
        return repo.read_sheet(path)

    def _read_pending(self, path: Path) -> ContextPendingItem | None:
        try:
            frontmatter, body = parse_markdown_document(path.read_text(encoding="utf-8"))
        except OSError:
            return None
        if not frontmatter:
            return None
        return ContextPendingItem(
            id=str(frontmatter.get("id") or path.stem),
            capture_kind=str(frontmatter.get("capture_kind") or "note"),
            title=str(frontmatter.get("title") or path.stem),
            content=body.strip(),
            path=str(path),
            status=str(frontmatter.get("status") or "pending"),
            metadata=dict(frontmatter.get("metadata") or {}),
            source=dict(frontmatter.get("source") or {}),
            confidence=float(frontmatter.get("confidence", 0.0)),
            session_id=frontmatter.get("session_id"),
            created_at=str(frontmatter.get("created_at") or ""),
            updated_at=str(frontmatter.get("updated_at") or frontmatter.get("created_at") or ""),
        )

    def _iter_events(self) -> list[ContextEvent]:
        events: list[ContextEvent] = []
        for path in sorted(self.context_root.glob("events/*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(ContextEvent.from_dict(payload))
        events.sort(key=lambda event: event.created_at)
        return events

    def _sheet_document(self, sheet: ContextSheet) -> tuple[str, dict[str, Any], str]:
        directory = KIND_DIRECTORIES.get(sheet.kind, sheet.kind)
        ref = f"{directory}/{sheet.slug}"
        document = _compact_join(
            [
                f"Title: {sheet.name}",
                f"Kind: {sheet.kind}",
                f"Status: {sheet.status}",
                sheet.body,
                f"Links: {', '.join(sheet.links)}" if sheet.links else "",
                f"Source refs: {', '.join(sheet.source_refs)}" if sheet.source_refs else "",
                f"Metadata: {_json_text(sheet.metadata)}" if sheet.metadata else "",
            ]
        )
        metadata = {
            "ref": ref,
            "title": sheet.name,
            "wing": directory,
            "room": "sheet",
            "kind": sheet.kind,
            "status": sheet.status,
            "source_file": sheet.path,
            "chunk_index": 0,
            "added_by": "butler",
            "filed_at": sheet.updated_at,
            "created_at": sheet.created_at,
            "updated_at": sheet.updated_at,
        }
        return document, metadata, _stable_id("sheet", ref)

    def _pending_document(self, pending: ContextPendingItem) -> tuple[str, dict[str, Any], str]:
        ref = f"pending/{pending.id}"
        room = _slugify(pending.capture_kind or "pending")
        document = _compact_join(
            [
                f"Pending capture: {pending.title}",
                f"Capture kind: {pending.capture_kind}",
                f"Status: {pending.status}",
                pending.content,
                f"Metadata: {_json_text(pending.metadata)}" if pending.metadata else "",
                f"Source: {_json_text(pending.source)}" if pending.source else "",
            ]
        )
        metadata = {
            "ref": ref,
            "title": pending.title,
            "wing": "pending",
            "room": room,
            "kind": "pending",
            "status": pending.status,
            "source_file": pending.path,
            "chunk_index": 0,
            "added_by": "butler",
            "filed_at": pending.updated_at or pending.created_at,
            "created_at": pending.created_at,
            "updated_at": pending.updated_at,
        }
        return document, metadata, _stable_id("pending", ref)

    def _event_document(self, event: ContextEvent) -> tuple[str, dict[str, Any], str]:
        ref = f"event/{event.id}"
        room = _slugify(event.event_type or "event")
        document = _compact_join(
            [
                f"Event: {event.summary}",
                f"Event type: {event.event_type}",
                f"Entity refs: {', '.join(event.entity_refs)}" if event.entity_refs else "",
                f"Payload: {_json_text(event.payload)}" if event.payload else "",
                f"Source: {_json_text(event.source)}" if event.source else "",
            ]
        )
        metadata = {
            "ref": ref,
            "title": event.summary or event.event_type,
            "wing": "events",
            "room": room,
            "kind": "event",
            "status": "recorded",
            "source_file": str(self.context_root / "events" / f"{event.created_at[:10]}.jsonl"),
            "chunk_index": 0,
            "added_by": "butler",
            "filed_at": event.created_at,
            "created_at": event.created_at,
            "updated_at": event.created_at,
        }
        return document, metadata, _stable_id("event", ref)
