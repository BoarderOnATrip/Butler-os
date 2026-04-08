#!/usr/bin/env python3
"""
Context repository for aiButler.

Canonical user-facing context lives in markdown sheets with JSON frontmatter.
Raw history and provenance live in append-only JSONL logs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.models import ContextEvent, ContextPendingItem, ContextSheet, utc_now

KIND_DIRECTORIES = {
    "person": "people",
    "organization": "organizations",
    "place": "places",
    "conversation": "conversations",
    "task": "tasks",
    "project": "projects",
    "artifact": "artifacts",
    "secret": "secrets",
}

ROOT_DIRECTORIES = [
    "people",
    "organizations",
    "places",
    "conversations",
    "projects",
    "tasks",
    "artifacts",
    "secrets",
    "pending",
    "maps",
    "events",
    "receipts",
    "indexes",
]


def slugify(value: str) -> str:
    """Generate a stable filesystem slug."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or "item"


def render_markdown_document(frontmatter: dict[str, Any], body: str) -> str:
    """Render markdown with JSON frontmatter."""
    rendered_body = body.rstrip()
    if rendered_body:
        rendered_body = f"{rendered_body}\n"
    return f"---\n{json.dumps(frontmatter, indent=2, default=str)}\n---\n\n{rendered_body}"


def parse_markdown_document(raw: str) -> tuple[dict[str, Any], str]:
    """Parse markdown with JSON frontmatter."""
    if not raw.startswith("---\n"):
        return {}, raw
    marker = "\n---\n"
    end = raw.find(marker, 4)
    if end == -1:
        return {}, raw

    frontmatter_raw = raw[4:end]
    body = raw[end + len(marker):].lstrip("\n")
    try:
        frontmatter = json.loads(frontmatter_raw)
    except json.JSONDecodeError:
        return {}, body

    return frontmatter if isinstance(frontmatter, dict) else {}, body


class ContextRepository:
    """Filesystem-backed markdown and JSONL context repository."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).expanduser()

    def ensure_layout(self) -> dict[str, Any]:
        created: list[str] = []
        for relative in ROOT_DIRECTORIES:
            path = self.base_dir / relative
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created.append(str(path))

        geojson_path = self.base_dir / "maps" / "places.geojson"
        if not geojson_path.exists():
            geojson_path.write_text(json.dumps({
                "type": "FeatureCollection",
                "features": [],
            }, indent=2))
            created.append(str(geojson_path))

        for relative in ("indexes/links.jsonl", "indexes/embeddings.jsonl"):
            path = self.base_dir / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("")
                created.append(str(path))

        return {
            "ok": True,
            "base_dir": str(self.base_dir),
            "created": created,
        }

    def _sheet_directory(self, kind: str) -> str:
        normalized_kind = kind.strip().lower()
        if normalized_kind not in KIND_DIRECTORIES:
            raise ValueError(f"Unsupported context sheet kind: {kind}")
        return KIND_DIRECTORIES[normalized_kind]

    def _sheet_path(self, kind: str, slug: str) -> Path:
        directory = self._sheet_directory(kind)
        return self.base_dir / directory / f"{slug}.md"

    def _pending_path(self, pending_id: str, created_at: str) -> Path:
        month = created_at[:7]
        return self.base_dir / "pending" / month / f"{pending_id}.md"

    def _event_log_path(self, created_at: str) -> Path:
        return self.base_dir / "events" / f"{created_at[:10]}.jsonl"

    def _append_jsonl(self, relative_path: Path, payload: dict[str, Any]) -> Path:
        relative_path.parent.mkdir(parents=True, exist_ok=True)
        with relative_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
        return relative_path

    def _append_link_record(self, payload: dict[str, Any]) -> None:
        self._append_jsonl(self.base_dir / "indexes" / "links.jsonl", payload)

    def _next_event_id(self) -> str:
        return f"ctxevent_{uuid4().hex[:12]}"

    def append_event(
        self,
        *,
        event_id: str,
        event_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        entity_refs: list[str] | None = None,
        session_id: str | None = None,
        created_at: str | None = None,
    ) -> ContextEvent:
        self.ensure_layout()
        event = ContextEvent(
            id=event_id,
            event_type=event_type,
            summary=summary,
            payload=payload or {},
            source=source or {},
            entity_refs=entity_refs or [],
            session_id=session_id,
            created_at=created_at or utc_now(),
        )
        self._append_jsonl(self._event_log_path(event.created_at), event.to_dict())

        for entity_ref in event.entity_refs:
            self._append_link_record({
                "kind": "event_entity_ref",
                "source_ref": event.id,
                "target_ref": entity_ref,
                "created_at": event.created_at,
            })
        return event

    def create_sheet(
        self,
        *,
        sheet_id: str,
        kind: str,
        name: str,
        body: str = "",
        slug: str | None = None,
        links: list[str] | None = None,
        source_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "active",
        confidence: float = 1.0,
        created_at: str | None = None,
    ) -> ContextSheet:
        self.ensure_layout()
        created_ts = created_at or utc_now()
        sheet_slug = slugify(slug or name)
        path = self._sheet_path(kind, sheet_slug)
        existed = path.exists()
        stored_body = body.strip()
        sheet = ContextSheet(
            id=sheet_id,
            kind=kind.strip().lower(),
            slug=sheet_slug,
            name=name,
            path=str(path),
            body=stored_body,
            status=status,
            confidence=confidence,
            links=links or [],
            source_refs=source_refs or [],
            metadata=metadata or {},
            last_confirmed_at=created_ts if status == "active" else None,
            created_at=created_ts,
            updated_at=created_ts,
        )

        if existed:
            existing = self.read_sheet(path)
            if existing:
                sheet.id = existing.id
                sheet.created_at = existing.created_at
                if existing.last_confirmed_at:
                    sheet.last_confirmed_at = existing.last_confirmed_at

        frontmatter = {
            "id": sheet.id,
            "kind": sheet.kind,
            "slug": sheet.slug,
            "name": sheet.name,
            "links": sheet.links,
            "source_refs": sheet.source_refs,
            "status": sheet.status,
            "confidence": sheet.confidence,
            "metadata": sheet.metadata,
            "last_confirmed_at": sheet.last_confirmed_at,
            "created_at": sheet.created_at,
            "updated_at": sheet.updated_at,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown_document(frontmatter, sheet.body), encoding="utf-8")

        sheet_ref = f"{self._sheet_directory(sheet.kind)}/{sheet.slug}"
        for target in sheet.links:
            self._append_link_record({
                "kind": "sheet_link",
                "source_ref": sheet_ref,
                "target_ref": target,
                "created_at": sheet.updated_at,
            })

        self.append_event(
            event_id=self._next_event_id(),
            event_type="context.sheet.updated" if existed else "context.sheet.created",
            summary=f"{'Updated' if existed else 'Created'} {sheet.kind} sheet {sheet.name}",
            payload={
                "kind": sheet.kind,
                "slug": sheet.slug,
                "path": str(path),
            },
            entity_refs=[sheet_ref, *sheet.source_refs],
            created_at=sheet.updated_at,
        )
        return sheet

    def create_pending_item(
        self,
        *,
        pending_id: str,
        capture_kind: str,
        title: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        confidence: float = 0.0,
        session_id: str | None = None,
        created_at: str | None = None,
    ) -> ContextPendingItem:
        self.ensure_layout()
        created_ts = created_at or utc_now()
        path = self._pending_path(pending_id, created_ts)
        item = ContextPendingItem(
            id=pending_id,
            capture_kind=capture_kind.strip().lower(),
            title=title,
            content=content.strip(),
            path=str(path),
            metadata=metadata or {},
            source=source or {},
            confidence=confidence,
            session_id=session_id,
            created_at=created_ts,
            updated_at=created_ts,
        )
        frontmatter = {
            "id": item.id,
            "kind": "pending",
            "capture_kind": item.capture_kind,
            "title": item.title,
            "status": item.status,
            "confidence": item.confidence,
            "session_id": item.session_id,
            "metadata": item.metadata,
            "source": item.source,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown_document(frontmatter, item.content), encoding="utf-8")

        self.append_event(
            event_id=self._next_event_id(),
            event_type="context.pending.captured",
            summary=f"Captured pending {item.capture_kind}: {item.title}",
            payload={
                "pending_id": item.id,
                "path": str(path),
                "capture_kind": item.capture_kind,
            },
            source=item.source,
            entity_refs=[f"pending/{item.id}"],
            session_id=item.session_id,
            created_at=item.created_at,
        )
        return item

    def read_pending_item(self, path: Path) -> ContextPendingItem | None:
        if not path.exists():
            return None
        frontmatter, body = parse_markdown_document(path.read_text(encoding="utf-8"))
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
            created_at=str(frontmatter.get("created_at") or utc_now()),
            updated_at=str(frontmatter.get("updated_at") or utc_now()),
        )

    def get_pending_item(self, pending_id: str) -> ContextPendingItem | None:
        self.ensure_layout()
        normalized_id = pending_id.strip()
        if not normalized_id:
            return None
        for path in sorted(self.base_dir.glob(f"pending/*/{normalized_id}.md")):
            item = self.read_pending_item(path)
            if item:
                return item
        return None

    def save_pending_item(
        self,
        item: ContextPendingItem,
        *,
        event_type: str = "context.pending.updated",
        summary: str = "",
        event_payload: dict[str, Any] | None = None,
    ) -> ContextPendingItem:
        self.ensure_layout()
        path = Path(item.path).expanduser() if item.path else self._pending_path(item.id, item.created_at)
        item.path = str(path)
        frontmatter = {
            "id": item.id,
            "kind": "pending",
            "capture_kind": item.capture_kind,
            "title": item.title,
            "status": item.status,
            "confidence": item.confidence,
            "session_id": item.session_id,
            "metadata": item.metadata,
            "source": item.source,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown_document(frontmatter, item.content), encoding="utf-8")

        if event_type:
            self.append_event(
                event_id=self._next_event_id(),
                event_type=event_type,
                summary=summary or f"Updated pending {item.capture_kind}: {item.title}",
                payload={
                    "pending_id": item.id,
                    "path": str(path),
                    "capture_kind": item.capture_kind,
                    **(event_payload or {}),
                },
                source=item.source,
                entity_refs=[f"pending/{item.id}"],
                session_id=item.session_id,
                created_at=item.updated_at,
            )
        return item

    def _pending_paths(self, pending_id: str) -> list[Path]:
        normalized_id = pending_id.strip()
        if not normalized_id:
            return []
        return sorted(self.base_dir.glob(f"pending/*/{normalized_id}.md"))

    def update_pending_item(
        self,
        pending_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        confidence: float | None = None,
        session_id: str | None = None,
    ) -> ContextPendingItem | None:
        self.ensure_layout()
        existing = self.get_pending_item(pending_id)
        if not existing:
            return None

        path = Path(existing.path)
        if not path.exists():
            return None

        frontmatter, body = parse_markdown_document(path.read_text(encoding="utf-8"))
        current = ContextPendingItem(
            id=str(frontmatter.get("id") or existing.id),
            capture_kind=str(frontmatter.get("capture_kind") or existing.capture_kind),
            title=str(frontmatter.get("title") or existing.title),
            content=body.strip(),
            path=str(path),
            status=str(frontmatter.get("status") or existing.status),
            metadata=dict(frontmatter.get("metadata") or existing.metadata or {}),
            source=dict(frontmatter.get("source") or existing.source or {}),
            confidence=float(frontmatter.get("confidence", existing.confidence)),
            session_id=frontmatter.get("session_id") or existing.session_id,
            created_at=str(frontmatter.get("created_at") or existing.created_at),
            updated_at=str(frontmatter.get("updated_at") or existing.updated_at),
        )

        if status is not None:
            current.status = status.strip().lower() or current.status
        if title is not None:
            current.title = title.strip() or current.title
        if content is not None:
            current.content = content.strip()
        if metadata is not None:
            current.metadata = {**current.metadata, **metadata}
        if source is not None:
            current.source = {**current.source, **source}
        if confidence is not None:
            current.confidence = float(confidence)
        if session_id is not None:
            current.session_id = session_id or None
        current.updated_at = utc_now()

        updated_frontmatter = {
            "id": current.id,
            "kind": "pending",
            "capture_kind": current.capture_kind,
            "title": current.title,
            "status": current.status,
            "confidence": current.confidence,
            "session_id": current.session_id,
            "metadata": current.metadata,
            "source": current.source,
            "created_at": current.created_at,
            "updated_at": current.updated_at,
        }
        path.write_text(render_markdown_document(updated_frontmatter, current.content), encoding="utf-8")
        return current

    def read_sheet(self, path: Path) -> ContextSheet | None:
        if not path.exists():
            return None
        frontmatter, body = parse_markdown_document(path.read_text(encoding="utf-8"))
        if not frontmatter:
            return None
        return ContextSheet(
            id=str(frontmatter.get("id") or path.stem),
            kind=str(frontmatter.get("kind") or "artifact"),
            slug=str(frontmatter.get("slug") or path.stem),
            name=str(frontmatter.get("name") or path.stem),
            path=str(path),
            body=body.strip(),
            status=str(frontmatter.get("status") or "active"),
            confidence=float(frontmatter.get("confidence", 1.0)),
            links=list(frontmatter.get("links") or []),
            source_refs=list(frontmatter.get("source_refs") or []),
            metadata=dict(frontmatter.get("metadata") or {}),
            last_confirmed_at=frontmatter.get("last_confirmed_at"),
            created_at=str(frontmatter.get("created_at") or utc_now()),
            updated_at=str(frontmatter.get("updated_at") or utc_now()),
        )

    def _iter_sheet_paths(self, kind: str | None = None) -> list[Path]:
        if kind:
            return sorted(self._sheet_path(kind, "*").parent.glob("*.md"))

        paths: list[Path] = []
        for directory in ROOT_DIRECTORIES:
            if directory in {"pending", "maps", "events", "receipts", "indexes"}:
                continue
            paths.extend((self.base_dir / directory).glob("*.md"))
        return sorted(paths)

    def list_sheets(self, *, kind: str | None = None, limit: int = 50) -> list[ContextSheet]:
        self.ensure_layout()
        sheets = [sheet for sheet in (self.read_sheet(path) for path in self._iter_sheet_paths(kind)) if sheet]
        sheets.sort(key=lambda sheet: (sheet.updated_at, sheet.created_at), reverse=True)
        return sheets[:limit]

    def list_pending_items(self, *, limit: int = 50) -> list[ContextPendingItem]:
        self.ensure_layout()
        items: list[ContextPendingItem] = []
        for path in sorted(self.base_dir.glob("pending/*/*.md")):
            item = self.read_pending_item(path)
            if item:
                items.append(item)
        items.sort(key=lambda item: (item.updated_at, item.created_at), reverse=True)
        return items[:limit]

    def list_events(self, *, limit: int = 50) -> list[ContextEvent]:
        self.ensure_layout()
        rows: list[dict[str, Any]] = []
        for path in sorted(self.base_dir.glob("events/*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rows.append(json.loads(line))

        events = [ContextEvent.from_dict(row) for row in rows]
        events.sort(key=lambda event: event.created_at, reverse=True)
        return events[:limit]
