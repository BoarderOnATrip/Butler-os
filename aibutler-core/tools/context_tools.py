#!/usr/bin/env python3
"""
aiButler context tools.

Thin wrappers around the runtime context repository so phone, desktop, and
future voice surfaces can capture and inspect context through the tool spine.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from runtime.context_repository import parse_markdown_document
from runtime.mempalace_adapter import ButlerMemPalaceIndex


def _get_runtime():
    from runtime.engine import get_default_runtime

    return get_default_runtime()


def _get_mempalace_index():
    runtime = _get_runtime()
    return ButlerMemPalaceIndex(context_root=runtime.context_repository.base_dir)


def _clean_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or "capture"


def _build_source(
    *,
    source_app: str = "",
    source_device: str = "",
    source_hardware: str = "",
    source_surface: str = "",
) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "app": _clean_text(source_app),
            "device": _clean_text(source_device),
            "hardware": _clean_text(source_hardware),
            "surface": _clean_text(source_surface),
        }.items()
        if value
    }


def _build_metadata(
    *,
    place_ref: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if _clean_text(place_ref):
        metadata["place_ref"] = _clean_text(place_ref)
    if extra:
        metadata.update({key: value for key, value in extra.items() if value not in ("", None, [], {})})
    return metadata


def _infer_extension(file_name: str, mime_type: str) -> str:
    if file_name:
        suffix = Path(file_name).suffix.lower()
        if suffix:
            return suffix

    normalized_mime = _clean_text(mime_type).lower()
    if normalized_mime:
        ext = mimetypes.guess_extension(normalized_mime)
        if ext:
            return ext.lower()
        if normalized_mime in {"image/heic", "image/heif"}:
            return ".heic"
        if normalized_mime.startswith("image/"):
            return ".jpg"
        if normalized_mime.startswith("video/"):
            return ".mp4"
        if normalized_mime.startswith("audio/"):
            return ".m4a"
        if normalized_mime == "application/pdf":
            return ".pdf"

    return ".bin"


def _safe_file_name(
    *,
    file_name: str,
    title: str,
    capture_kind: str,
    mime_type: str,
) -> str:
    raw_name = Path(file_name).name if file_name else ""
    stem = Path(raw_name).stem if raw_name else ""
    if not stem:
        stem = title or capture_kind or "capture"
    safe_stem = _slugify(stem)
    extension = _infer_extension(raw_name, mime_type)
    return f"{safe_stem}{extension}"


def _strip_data_uri_prefix(data_base64: str) -> str:
    payload = _clean_text(data_base64)
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    return "".join(payload.split())


def _decode_capture_bytes(data_base64: str) -> bytes:
    payload = _strip_data_uri_prefix(data_base64)
    if not payload:
        raise ValueError("data_base64 is empty")
    try:
        return base64.b64decode(payload, validate=True)
    except binascii.Error as exc:
        raise ValueError("data_base64 is not valid base64") from exc


def _persist_capture_file(
    runtime,
    *,
    title: str,
    capture_kind: str,
    file_name: str,
    mime_type: str,
    data_base64: str,
) -> dict[str, Any]:
    raw_bytes = _decode_capture_bytes(data_base64)
    repo_root = runtime.context_repository.base_dir
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    capture_id = f"capture_{uuid4().hex[:12]}"
    upload_dir = repo_root / "inbox" / "uploads" / month / capture_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_file_name(
        file_name=file_name,
        title=title,
        capture_kind=capture_kind,
        mime_type=mime_type,
    )
    final_path = upload_dir / safe_name
    temp_path = final_path.with_name(f".{final_path.name}.tmp-{capture_id}")
    temp_path.write_bytes(raw_bytes)
    temp_path.replace(final_path)

    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        relative_path = str(final_path.relative_to(repo_root))
    except ValueError:
        relative_path = str(final_path)

    return {
        "capture_id": capture_id,
        "byte_size": len(raw_bytes),
        "sha256": digest,
        "saved_file_path": str(final_path),
        "saved_file_relpath": relative_path,
        "saved_file_name": final_path.name,
    }


def _pins_path(runtime) -> Path:
    return runtime.context_repository.base_dir / "indexes" / "pins.json"


def _load_pins(runtime) -> dict[str, dict[str, Any]]:
    path = _pins_path(runtime)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list):
        return {}
    return {
        str(item.get("ref")): dict(item)
        for item in payload
        if isinstance(item, dict) and item.get("ref")
    }


def _save_pins(runtime, pins: dict[str, dict[str, Any]]) -> Path:
    path = _pins_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            sorted(pins.values(), key=lambda item: str(item.get("updated_at", "")), reverse=True),
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path


def _resolve_ref_path(runtime, ref: str) -> str:
    repo_root = runtime.context_repository.base_dir
    normalized_ref = _clean_text(ref)
    if not normalized_ref:
        return ""

    if normalized_ref.startswith("pending/"):
        pending_id = normalized_ref.split("/", 1)[1]
        matches = sorted(repo_root.glob(f"pending/*/{pending_id}.md"))
        return str(matches[0]) if matches else ""

    candidate = repo_root / f"{normalized_ref}.md"
    return str(candidate) if candidate.exists() else ""


def _load_ref_snapshot(runtime, ref: str) -> dict[str, Any]:
    normalized_ref = _clean_text(ref)
    if not normalized_ref:
        return {}

    path = _resolve_ref_path(runtime, normalized_ref)
    if not path:
        return {"ref": normalized_ref, "title": normalized_ref}

    file_path = Path(path)
    if normalized_ref.startswith("pending/"):
        frontmatter, body = parse_markdown_document(file_path.read_text(encoding="utf-8"))
        return {
            "ref": normalized_ref,
            "kind": "pending",
            "title": str(frontmatter.get("title") or file_path.stem),
            "summary": body.strip(),
            "path": str(file_path),
            "created_at": str(frontmatter.get("created_at") or ""),
            "updated_at": str(frontmatter.get("updated_at") or ""),
            "status": str(frontmatter.get("status") or "pending"),
        }

    sheet = runtime.context_repository.read_sheet(file_path)
    if not sheet:
        return {"ref": normalized_ref, "title": normalized_ref, "path": str(file_path)}
    return {
        "ref": normalized_ref,
        "kind": sheet.kind,
        "title": sheet.name,
        "summary": sheet.body.strip(),
        "path": sheet.path,
        "created_at": sheet.created_at,
        "updated_at": sheet.updated_at,
        "status": sheet.status,
    }


def _event_feed_item(runtime, event, pins: dict[str, dict[str, Any]]) -> dict[str, Any]:
    primary_ref = next((ref for ref in event.entity_refs if _clean_text(ref)), "")
    snapshot = _load_ref_snapshot(runtime, primary_ref) if primary_ref else {}
    pin_record = next((pins[ref] for ref in event.entity_refs if ref in pins), None)

    payload_summary = ""
    for key in ("summary", "content", "next_action", "title"):
        value = event.payload.get(key) if isinstance(event.payload, dict) else None
        if _clean_text(str(value) if value is not None else ""):
            payload_summary = _clean_text(str(value))
            break

    return {
        "id": event.id,
        "ref": primary_ref,
        "kind": _clean_text(snapshot.get("kind")) or event.event_type,
        "title": _clean_text(snapshot.get("title")) or event.summary,
        "summary": payload_summary or _clean_text(snapshot.get("summary")) or event.summary,
        "path": _clean_text(snapshot.get("path")),
        "created_at": event.created_at,
        "updated_at": event.created_at,
        "event_type": event.event_type,
        "entity_refs": list(event.entity_refs),
        "pinned": bool(pin_record),
        "pin_label": _clean_text(pin_record.get("label")) if pin_record else "",
        "pin_note": _clean_text(pin_record.get("note")) if pin_record else "",
    }


def _pin_feed_item(runtime, pin_record: dict[str, Any]) -> dict[str, Any]:
    ref = _clean_text(pin_record.get("ref"))
    snapshot = _load_ref_snapshot(runtime, ref)
    return {
        "id": f"pin::{ref}",
        "ref": ref,
        "kind": _clean_text(snapshot.get("kind")) or _clean_text(pin_record.get("kind")) or "pinned",
        "title": _clean_text(pin_record.get("label")) or _clean_text(snapshot.get("title")) or ref,
        "summary": _clean_text(pin_record.get("note")) or _clean_text(snapshot.get("summary")),
        "path": _clean_text(snapshot.get("path")) or _clean_text(pin_record.get("path")),
        "created_at": _clean_text(pin_record.get("updated_at")) or _clean_text(snapshot.get("updated_at")),
        "updated_at": _clean_text(pin_record.get("updated_at")) or _clean_text(snapshot.get("updated_at")),
        "event_type": "context.pin",
        "entity_refs": [ref],
        "pinned": True,
        "pin_label": _clean_text(pin_record.get("label")),
        "pin_note": _clean_text(pin_record.get("note")),
    }


def _truncate_text(value: str, limit: int = 140) -> str:
    normalized = _clean_text(value)
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _parse_datetime(value: str | None) -> datetime | None:
    raw = _clean_text(value)
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pending_review_score(item: dict[str, Any]) -> int:
    confidence = float(item.get("confidence", 0.0) or 0.0)
    status = _clean_text(str(item.get("status") or "pending")).lower()
    created_at = _parse_datetime(str(item.get("created_at") or ""))
    updated_at = _parse_datetime(str(item.get("updated_at") or ""))
    score = int((1.0 - confidence) * 60)
    score += 4 if status == "pending" else 2

    anchor = updated_at or created_at
    if anchor:
        age_days = max(0, (datetime.now(timezone.utc) - anchor).days)
        score += min(30, age_days * 2)
    return score


def _pending_review_action(item: dict[str, Any]) -> str:
    capture_kind = _clean_text(str(item.get("capture_kind") or "")).lower()
    if capture_kind in {"person", "contact"}:
        return "promote to person"
    if capture_kind in {"task", "todo", "reminder"}:
        return "promote to task"
    if capture_kind in {"receipt", "image", "photo", "screenshot", "document", "file", "video", "audio"}:
        return "promote to artifact"
    return "review or promote"


def _defer_until_value(defer_until: str = "", defer_for_days: int | None = None) -> str | None:
    explicit = _parse_datetime(defer_until)
    if explicit:
        return explicit.isoformat()
    if defer_for_days is None:
        return None
    try:
        days = int(defer_for_days)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _infer_promoted_kind(item: dict[str, Any], requested_kind: str = "") -> str:
    normalized_requested = _clean_text(requested_kind).lower()
    if normalized_requested:
        return normalized_requested

    capture_kind = _clean_text(str(item.get("capture_kind") or "")).lower()
    if capture_kind in {"person", "contact"}:
        return "person"
    if capture_kind in {"task", "todo", "reminder"}:
        return "task"
    if capture_kind in {"secret", "credential", "password"}:
        return "secret"
    if capture_kind in {"place", "location"}:
        return "place"
    if capture_kind in {"conversation", "thread", "message", "chat"}:
        return "conversation"
    return "artifact"


def _build_promoted_body(
    *,
    title: str,
    pending_item: dict[str, Any],
    promoted_kind: str,
    note: str = "",
) -> str:
    metadata = dict(pending_item.get("metadata") or {})
    source = dict(pending_item.get("source") or {})
    lines = [f"# {title}", "", f"## Promoted From Pending", f"- Pending ref: pending/{pending_item.get('id')}"]
    lines.append(f"- Capture kind: {pending_item.get('capture_kind') or 'note'}")
    lines.append(f"- Promoted kind: {promoted_kind}")
    lines.append(f"- Original status: {pending_item.get('status') or 'pending'}")
    lines.append(f"- Confidence: {float(pending_item.get('confidence', 0.0) or 0.0):.2f}")
    if metadata:
        lines.extend(["", "## Metadata", json.dumps(metadata, indent=2, default=str)])
    if source:
        lines.extend(["", "## Source", json.dumps(source, indent=2, default=str)])
    content = _clean_text(str(pending_item.get("content") or ""))
    if content:
        lines.extend(["", "## Content", content])
    if note:
        lines.extend(["", "## Review Note", note])
    return "\n".join(lines).strip()


def _graph_accent(*, kind: str, priority: str = "", pinned: bool = False, overdue: bool = False) -> str:
    normalized_priority = _clean_text(priority).lower()
    normalized_kind = _clean_text(kind).lower()

    if pinned:
        return "mint"
    if overdue or normalized_priority == "critical":
        return "rose"
    if normalized_priority == "high":
        return "amber"
    if normalized_kind == "pending":
        return "gold"
    if normalized_kind == "signal":
        return "sky"
    return "slate"


_LINKED_ENTITY_KINDS = {"organization", "place", "conversation"}
_LINKED_ENTITY_PREFIXES = {
    "organizations/": "organization",
    "organization/": "organization",
    "places/": "place",
    "place/": "place",
    "conversations/": "conversation",
    "conversation/": "conversation",
}


def _flatten_ref_values(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, str):
        cleaned = _clean_text(value)
        if cleaned:
            refs.append(cleaned)
        return refs
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = _clean_text(str(key)).lower()
            if normalized_key in {"ref", "refs"} or normalized_key.endswith("_ref") or normalized_key.endswith("_refs"):
                refs.extend(_flatten_ref_values(nested))
        return refs
    if isinstance(value, (list, tuple, set)):
        for item in value:
            refs.extend(_flatten_ref_values(item))
    return refs


def _collect_person_link_refs(sheet) -> list[str]:
    metadata = dict(sheet.metadata or {})
    refs: list[str] = []
    seen: set[str] = set()

    def add_candidates(value: Any) -> None:
        for ref in _flatten_ref_values(value):
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)

    add_candidates(sheet.links)
    add_candidates(sheet.source_refs)

    for key, value in metadata.items():
        normalized_key = _clean_text(str(key)).lower()
        if normalized_key in {"links", "linked", "linked_ref", "linked_refs", "linked_entity", "linked_entities", "related", "related_ref", "related_refs", "connections", "connection_ref", "connection_refs", "associations", "association_ref", "association_refs", "organization_ref", "organization_refs", "organizations", "org_ref", "org_refs", "orgs", "place_ref", "place_refs", "places", "conversation_ref", "conversation_refs", "conversations"} or normalized_key.endswith("_ref") or normalized_key.endswith("_refs"):
            add_candidates(value)

    return refs


def _linked_entity_kind(ref: str, snapshot: dict[str, Any], pin_record: dict[str, Any] | None) -> str:
    normalized_ref = _clean_text(ref).lower()
    for prefix, kind in _LINKED_ENTITY_PREFIXES.items():
        if normalized_ref.startswith(prefix):
            return kind

    snapshot_kind = _clean_text(snapshot.get("kind")).lower()
    if snapshot_kind in _LINKED_ENTITY_KINDS:
        return snapshot_kind

    if pin_record:
        pinned_kind = _clean_text(pin_record.get("kind")).lower()
        if pinned_kind in _LINKED_ENTITY_KINDS:
            return pinned_kind

    return ""


def _linked_entity_node(runtime, ref: str, pins: dict[str, dict[str, Any]]) -> dict[str, Any]:
    normalized_ref = _clean_text(ref)
    if not normalized_ref:
        return {}

    snapshot = _load_ref_snapshot(runtime, normalized_ref)
    pin_record = pins.get(normalized_ref)
    kind = _linked_entity_kind(normalized_ref, snapshot, pin_record)
    if kind not in _LINKED_ENTITY_KINDS:
        return {}

    title = _clean_text(pin_record.get("label")) if pin_record else ""
    if not title:
        title = _clean_text(snapshot.get("title")) or normalized_ref
    summary = _clean_text(pin_record.get("note")) if pin_record else ""
    if not summary:
        summary = _clean_text(snapshot.get("summary"))
    path = _clean_text(snapshot.get("path")) or _clean_text(pin_record.get("path"))

    return {
        "id": normalized_ref,
        "ref": normalized_ref,
        "title": title,
        "subtitle": f"Linked {kind}",
        "summary": _truncate_text(summary, 120),
        "kind": kind,
        "lane": "linked",
        "accent": _graph_accent(kind=kind, pinned=bool(pin_record)),
        "pinned": bool(pin_record),
        "priority": "",
        "score": 62 if kind == "organization" else 60,
        "due_label": "",
        "meta": {
            "path": path,
        },
    }


def context_graph_snapshot(
    relationship_limit: int = 6,
    pending_limit: int = 4,
    signal_limit: int = 5,
    pin_limit: int = 4,
) -> dict:
    """Return a relationship-first context map snapshot for mobile and desktop shells."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    from tools.relationship_tools import relationship_list_followups

    pins = _load_pins(runtime)
    followup_result = relationship_list_followups(limit=max(relationship_limit * 2, relationship_limit))
    followups = list(followup_result.get("output") or [])
    followups.sort(
        key=lambda item: (
            0 if item.get("pinned") else 1,
            -int(item.get("score", 0) or 0),
            _clean_text(str(item.get("full_name") or item.get("person_name") or item.get("name"))).lower(),
        )
    )
    followups = followups[: max(0, relationship_limit)]

    pending_items = [item.to_dict() for item in runtime.list_pending_context(limit=max(0, pending_limit))]
    events = runtime.list_context_events(limit=max(signal_limit * 5, 30))

    nodes: list[dict[str, Any]] = [
        {
            "id": "hub::today",
            "ref": "hub::today",
            "title": "Today",
            "subtitle": "Butler context map",
            "summary": "Your strongest relationship threads, pending captures, and recent signals in one place.",
            "kind": "hub",
            "lane": "hub",
            "accent": "mint",
            "pinned": False,
            "score": 100,
        }
    ]
    edges: list[dict[str, Any]] = []
    seen_ids = {"hub::today"}
    ref_to_node_id: dict[str, str] = {"hub::today": "hub::today"}
    linked_person_sources: list[tuple[str, Any]] = []

    def add_node(node: dict[str, Any]) -> bool:
        node_id = _clean_text(str(node.get("id")))
        if not node_id or node_id in seen_ids:
            return False
        seen_ids.add(node_id)
        nodes.append(node)
        ref = _clean_text(str(node.get("ref") or ""))
        if ref and ref not in ref_to_node_id:
            ref_to_node_id[ref] = node_id
        return True

    def connect(source: str, target: str, *, kind: str, label: str = "") -> None:
        if source == target:
            return
        edge_id = f"{source}->{target}:{kind}"
        if edge_id in seen_ids:
            return
        seen_ids.add(edge_id)
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "kind": kind,
                "label": _clean_text(label),
            }
        )

    focus_ref = ""
    for item in followups:
        person_ref = _clean_text(str(item.get("person_ref") or ""))
        if not person_ref:
            continue
        person_name = _clean_text(str(item.get("full_name") or item.get("person_name") or item.get("name") or "Relationship"))
        subtitle = " | ".join(
            [part for part in (_clean_text(str(item.get("company"))), _clean_text(str(item.get("role")))) if part]
        ) or _clean_text(str(item.get("channel") or "relationship"))
        summary = _clean_text(str(item.get("next_action") or item.get("thread_summary") or item.get("open_loop") or ""))
        added = add_node(
            {
                "id": person_ref,
                "ref": person_ref,
                "title": person_name,
                "subtitle": subtitle,
                "summary": _truncate_text(summary, 120),
                "kind": "person",
                "lane": "relationships",
                "accent": _graph_accent(
                    kind="person",
                    priority=str(item.get("priority") or ""),
                    pinned=bool(item.get("pinned")),
                    overdue=bool(item.get("overdue")),
                ),
                "pinned": bool(item.get("pinned")),
                "priority": _clean_text(str(item.get("priority") or "")),
                "score": int(item.get("score", 0) or 0),
                "due_label": _clean_text(str(item.get("due_label") or "")),
                "meta": {
                    "channel": _clean_text(str(item.get("channel") or "")),
                    "stage": _clean_text(str(item.get("stage") or "")),
                    "relationship_type": _clean_text(str(item.get("relationship_type") or "")),
                    "next_action_due_at": item.get("next_action_due_at"),
                },
            }
        )
        if added:
            connect("hub::today", person_ref, kind="relationship", label=_clean_text(str(item.get("due_label") or "")))
            if not focus_ref:
                focus_ref = person_ref
            sheet_path = _clean_text(str(item.get("path") or ""))
            if sheet_path:
                person_sheet = runtime.context_repository.read_sheet(Path(sheet_path))
                if person_sheet:
                    linked_person_sources.append((person_ref, person_sheet))

    for person_ref, person_sheet in linked_person_sources:
        seen_person_link_refs: set[str] = set()
        for linked_ref in _collect_person_link_refs(person_sheet):
            if linked_ref in seen_person_link_refs:
                continue
            seen_person_link_refs.add(linked_ref)
            linked_node = _linked_entity_node(runtime, linked_ref, pins)
            if not linked_node:
                continue
            add_node(linked_node)
            connect(person_ref, linked_ref, kind="link", label=_clean_text(str(linked_node.get("kind") or "")))

    sorted_pins = sorted(
        pins.values(),
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )
    pin_nodes_added = 0
    for pin_record in sorted_pins:
        if pin_nodes_added >= max(0, pin_limit):
            break
        ref = _clean_text(str(pin_record.get("ref") or ""))
        if not ref or ref in ref_to_node_id:
            continue
        snapshot = _load_ref_snapshot(runtime, ref)
        title = _clean_text(snapshot.get("title")) or _clean_text(pin_record.get("label")) or ref
        kind = _clean_text(snapshot.get("kind")) or _clean_text(pin_record.get("kind")) or "anchor"
        lane = "pending" if kind == "pending" else "anchors"
        added = add_node(
            {
                "id": ref,
                "ref": ref,
                "title": title,
                "subtitle": _clean_text(pin_record.get("label")) or f"Pinned {kind}",
                "summary": _truncate_text(_clean_text(pin_record.get("note")) or _clean_text(snapshot.get("summary")), 120),
                "kind": kind,
                "lane": lane,
                "accent": _graph_accent(kind=kind, pinned=True),
                "pinned": True,
                "priority": "",
                "score": 70,
                "due_label": "",
                "meta": {
                    "path": _clean_text(snapshot.get("path")) or _clean_text(pin_record.get("path")),
                },
            }
        )
        if added:
            pin_nodes_added += 1
            connect("hub::today", ref, kind="pin", label="Pinned")

    for item in pending_items:
        pending_ref = f"pending/{item['id']}"
        if pending_ref in ref_to_node_id:
            continue
        added = add_node(
            {
                "id": pending_ref,
                "ref": pending_ref,
                "title": _clean_text(str(item.get("title") or item["id"])),
                "subtitle": _clean_text(str(item.get("capture_kind") or "pending review")),
                "summary": _truncate_text(str(item.get("content") or ""), 120),
                "kind": "pending",
                "lane": "pending",
                "accent": _graph_accent(kind="pending"),
                "pinned": pending_ref in pins,
                "priority": "",
                "score": int(float(item.get("confidence", 0.0) or 0.0) * 100),
                "due_label": "Review pending",
                "meta": {
                    "confidence": item.get("confidence"),
                    "created_at": item.get("created_at"),
                },
            }
        )
        if added:
            connect("hub::today", pending_ref, kind="pending", label="Pending review")

    signal_nodes_added = 0
    seen_signal_refs: set[str] = set()
    for event in events:
        if signal_nodes_added >= max(0, signal_limit):
            break
        feed_item = _event_feed_item(runtime, event, pins)
        entity_refs = [ref for ref in list(feed_item.get("entity_refs") or []) if _clean_text(str(ref))]
        if feed_item.get("event_type") == "context.pin.updated":
            continue
        parent_node_id = next((ref_to_node_id[ref] for ref in entity_refs if ref in ref_to_node_id and ref != "hub::today"), "")
        parent_ref = next((ref for ref in entity_refs if ref != "hub::today"), "")
        if parent_ref and parent_ref in seen_signal_refs:
            continue

        signal_id = f"signal::{feed_item['id']}"
        added = add_node(
            {
                "id": signal_id,
                "ref": _clean_text(str(feed_item.get("ref") or signal_id)),
                "title": _clean_text(str(feed_item.get("title") or "Recent signal")),
                "subtitle": _clean_text(str(feed_item.get("event_type") or "activity")),
                "summary": _truncate_text(str(feed_item.get("summary") or ""), 110),
                "kind": "signal",
                "lane": "signals",
                "accent": _graph_accent(kind="signal", pinned=bool(feed_item.get("pinned"))),
                "pinned": bool(feed_item.get("pinned")),
                "priority": "",
                "score": 40,
                "due_label": _clean_text(str(feed_item.get("updated_at") or feed_item.get("created_at") or "")),
                "meta": {
                    "entity_refs": entity_refs,
                },
            }
        )
        if not added:
            continue

        signal_nodes_added += 1
        if parent_node_id:
            connect(parent_node_id, signal_id, kind="signal", label=_clean_text(str(feed_item.get("event_type") or "")))
            seen_signal_refs.add(parent_ref)
        else:
            connect("hub::today", signal_id, kind="signal", label=_clean_text(str(feed_item.get("event_type") or "")))

    overdue_count = sum(1 for item in followups if bool(item.get("overdue")))
    pending_count = len([node for node in nodes if node.get("kind") == "pending"])
    pinned_count = len([node for node in nodes if node.get("pinned")])
    relationship_count = len([node for node in nodes if node.get("lane") == "relationships"])
    signal_count = len([node for node in nodes if node.get("kind") == "signal"])
    linked_count = len([node for node in nodes if node.get("lane") == "linked"])
    linked_organization_count = len([node for node in nodes if node.get("kind") == "organization" and node.get("lane") == "linked"])
    linked_place_count = len([node for node in nodes if node.get("kind") == "place" and node.get("lane") == "linked"])
    linked_conversation_count = len([node for node in nodes if node.get("kind") == "conversation" and node.get("lane") == "linked"])

    if focus_ref and focus_ref in ref_to_node_id:
        focus_node = next((node for node in nodes if node["id"] == ref_to_node_id[focus_ref]), None)
        focus_title = _clean_text(focus_node.get("title") if focus_node else "")
        due_label = _clean_text(focus_node.get("due_label") if focus_node else "")
        spotlight = f"{focus_title} is the strongest live thread."
        if due_label:
            spotlight += f" {due_label}."
    elif pending_count:
        first_pending = next((node for node in nodes if node.get("kind") == "pending"), None)
        spotlight = f"{_clean_text(first_pending.get('title') if first_pending else 'Pending review')} needs clarification."
    else:
        spotlight = "Log an interaction or capture an item to start building your living context map."

    if overdue_count:
        spotlight += f" {overdue_count} follow-up{'s are' if overdue_count != 1 else ' is'} overdue."

    return {
        "ok": True,
        "output": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "focus_ref": focus_ref,
            "spotlight": spotlight.strip(),
            "stats": {
                "pinned": pinned_count,
                "relationships": relationship_count,
                "linked_entities": linked_count,
                "linked_organizations": linked_organization_count,
                "linked_places": linked_place_count,
                "linked_conversations": linked_conversation_count,
                "pending": pending_count,
                "signals": signal_count,
                "overdue": overdue_count,
            },
            "nodes": nodes,
            "edges": edges,
        },
        "error": None,
    }


def capture_pending_context(
    capture_kind: str,
    title: str,
    content: str = "",
    confidence: float = 0.0,
    source_app: str = "",
    source_device: str = "",
    source_hardware: str = "",
    source_surface: str = "",
    place_ref: str = "",
    session_id: str = "",
) -> dict:
    """Capture a low-confidence or unresolved item into the pending context queue."""
    runtime = _get_runtime()
    source = _build_source(
        source_app=source_app,
        source_device=source_device,
        source_hardware=source_hardware,
        source_surface=source_surface,
    )
    metadata = _build_metadata(place_ref=place_ref)

    item = runtime.capture_pending_context(
        capture_kind=capture_kind,
        title=title,
        content=content,
        metadata=metadata,
        source=source,
        confidence=confidence,
        session_id=session_id or None,
    )
    return {
        "ok": True,
        "output": item.to_dict(),
        "error": None,
    }


def capture_context_artifact(
    capture_kind: str,
    title: str,
    content: str = "",
    file_name: str = "",
    mime_type: str = "",
    data_base64: str = "",
    source_app: str = "",
    source_device: str = "",
    source_hardware: str = "",
    source_surface: str = "",
    place_ref: str = "",
    session_id: str = "",
) -> dict:
    """Capture a phone photo or attachment, persist it, and enqueue it for review."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    normalized_kind = _clean_text(capture_kind)
    normalized_title = _clean_text(title)
    normalized_content = _clean_text(content)
    normalized_file_name = _clean_text(file_name)
    normalized_mime_type = _clean_text(mime_type)
    normalized_place_ref = _clean_text(place_ref)
    normalized_session_id = _clean_text(session_id)

    if not normalized_kind:
        return {"ok": False, "output": "", "error": "capture_kind is required"}
    if not normalized_title:
        return {"ok": False, "output": "", "error": "title is required"}

    source = _build_source(
        source_app=source_app,
        source_device=source_device,
        source_hardware=source_hardware,
        source_surface=source_surface,
    )
    metadata = _build_metadata(place_ref=normalized_place_ref)

    saved_file: dict[str, Any] | None = None
    if _clean_text(data_base64):
        try:
            saved_file = _persist_capture_file(
                runtime,
                title=normalized_title,
                capture_kind=normalized_kind,
                file_name=normalized_file_name,
                mime_type=normalized_mime_type,
                data_base64=data_base64,
            )
            metadata.update(saved_file)
            metadata["file_name"] = normalized_file_name or saved_file["saved_file_name"]
            metadata["mime_type"] = normalized_mime_type
            metadata["capture_source"] = source
        except (ValueError, OSError, binascii.Error) as exc:
            return {
                "ok": False,
                "output": "",
                "error": f"Failed to ingest capture file: {exc}",
            }

    if not normalized_content:
        summary_bits = [
            f"capture_kind: {normalized_kind}",
            f"title: {normalized_title}",
        ]
        if saved_file:
            summary_bits.append(f"saved_file_path: {saved_file['saved_file_path']}")
        normalized_content = "\n".join(summary_bits)

    item = runtime.capture_pending_context(
        capture_kind=normalized_kind,
        title=normalized_title,
        content=normalized_content,
        metadata=metadata,
        source=source,
        confidence=0.2 if saved_file else 0.0,
        session_id=normalized_session_id or None,
    )

    event_payload = {
        "capture_kind": normalized_kind,
        "title": normalized_title,
        "content": normalized_content,
        "pending_id": item.id,
        "source_surface": _clean_text(source_surface),
        "source_device": _clean_text(source_device),
        "source_app": _clean_text(source_app),
        "place_ref": normalized_place_ref,
        "saved_file": saved_file,
        "mime_type": normalized_mime_type,
        "file_name": normalized_file_name,
    }
    event = runtime.append_context_event(
        event_type="context.capture.ingested",
        summary=f"Ingested {normalized_kind} capture: {normalized_title}",
        payload=event_payload,
        source=source,
        entity_refs=[f"pending/{item.id}"],
        session_id=normalized_session_id or None,
    )

    output = {
        "pending_item": item.to_dict(),
        "provenance_event": event.to_dict(),
        "saved_file_path": saved_file["saved_file_path"] if saved_file else None,
        "saved_file_relpath": saved_file["saved_file_relpath"] if saved_file else None,
        "saved_file_name": saved_file["saved_file_name"] if saved_file else None,
        "byte_size": saved_file["byte_size"] if saved_file else 0,
        "sha256": saved_file["sha256"] if saved_file else None,
        "context_root": str(runtime.context_repository.base_dir),
    }
    return {
        "ok": True,
        "output": output,
        "error": None,
    }


def list_pending_context(limit: int = 10) -> dict:
    """List pending context items for quick review surfaces."""
    runtime = _get_runtime()
    items = [item.to_dict() for item in runtime.list_pending_context(limit=limit)]
    return {
        "ok": True,
        "output": items,
        "error": None,
    }


def context_review_queue(limit: int = 20, include_relationships: bool = True) -> dict:
    """Return a combined review queue for pending context and relationship follow-ups."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    queue: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for item in [item.to_dict() for item in runtime.list_pending_context(limit=max(limit * 2, limit))]:
        status = _clean_text(str(item.get("status") or "pending")).lower()
        if status in {"dismissed", "promoted"}:
            continue

        metadata = dict(item.get("metadata") or {})
        defer_until = _parse_datetime(str(metadata.get("defer_until") or metadata.get("deferred_until") or ""))
        if status == "deferred" and defer_until and defer_until > now:
            continue

        queue.append(
            {
                "id": f"pending::{item['id']}",
                "ref": f"pending/{item['id']}",
                "kind": "pending",
                "title": _clean_text(str(item.get("title") or item["id"])),
                "summary": _truncate_text(str(item.get("content") or ""), 160),
                "status": status,
                "capture_kind": _clean_text(str(item.get("capture_kind") or "note")),
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "source": item.get("source") or {},
                "metadata": metadata,
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "score": _pending_review_score(item),
                "due_label": "Review pending" if status == "pending" else "Revisit deferred item",
                "action_hint": _pending_review_action(item),
            }
        )

    if include_relationships:
        from tools.relationship_tools import relationship_list_followups

        followups = list(relationship_list_followups(limit=max(limit, 5)).get("output") or [])
        for item in followups:
            if not isinstance(item, dict):
                continue
            due_label = _clean_text(str(item.get("due_label") or ""))
            queue.append(
                {
                    "id": f"relationship::{item.get('person_ref') or item.get('id')}",
                    "ref": _clean_text(str(item.get("person_ref") or item.get("id") or "")),
                    "kind": "relationship",
                    "title": _clean_text(str(item.get("full_name") or item.get("person_name") or "Relationship")),
                    "summary": _truncate_text(
                        str(item.get("next_action") or item.get("thread_summary") or item.get("open_loop") or ""),
                        160,
                    ),
                    "status": "overdue" if item.get("overdue") else "follow_up",
                    "capture_kind": "relationship",
                    "confidence": 1.0,
                    "source": {
                        "channel": _clean_text(str(item.get("channel") or "")),
                        "stage": _clean_text(str(item.get("stage") or "")),
                    },
                    "metadata": {
                        "priority": _clean_text(str(item.get("priority") or "")),
                        "due_label": due_label,
                        "next_action_due_at": item.get("next_action_due_at"),
                        "company": _clean_text(str(item.get("company") or "")),
                        "role": _clean_text(str(item.get("role") or "")),
                    },
                    "created_at": item.get("updated_at") or item.get("last_touch_at"),
                    "updated_at": item.get("updated_at") or item.get("last_touch_at"),
                    "score": int(item.get("score", 0) or 0) + (20 if item.get("overdue") else 0),
                    "due_label": due_label or "Relationship follow-up",
                    "action_hint": "reply or schedule follow-up",
                }
            )

    queue.sort(
        key=lambda item: (
            -int(item.get("score", 0) or 0),
            _clean_text(str(item.get("updated_at") or item.get("created_at") or "")),
            _clean_text(str(item.get("title") or "")).lower(),
        )
    )

    return {
        "ok": True,
        "output": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": queue[:limit],
            "stats": {
                "pending": sum(1 for item in queue if item.get("kind") == "pending"),
                "relationship_followups": sum(1 for item in queue if item.get("kind") == "relationship"),
                "total": len(queue),
            },
        },
        "error": None,
    }


def promote_pending_context(
    pending_id: str,
    kind: str = "",
    title: str = "",
    note: str = "",
    session_id: str = "",
) -> dict:
    """Promote a pending item into canonical context and mark it reviewed."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    pending_item = runtime.get_pending_context_item(pending_id)
    if not pending_item:
        return {"ok": False, "output": "", "error": "pending item not found"}

    pending_data = pending_item.to_dict()
    promoted_kind = _infer_promoted_kind(pending_data, kind)
    promoted_title = _clean_text(title) or _clean_text(pending_data.get("title") or pending_data.get("capture_kind") or pending_id)
    promoted_body = _build_promoted_body(
        title=promoted_title,
        pending_item=pending_data,
        promoted_kind=promoted_kind,
        note=note,
    )
    source_refs = [f"pending/{pending_item.id}"]
    metadata = dict(pending_data.get("metadata") or {})
    metadata.update({
        "promoted_from_pending": pending_item.id,
        "pending_status": pending_item.status,
        "promoted_kind": promoted_kind,
    })

    sheet = runtime.create_context_sheet(
        kind=promoted_kind,
        name=promoted_title,
        body=promoted_body,
        source_refs=source_refs,
        metadata=metadata,
        status="active",
        confidence=max(float(pending_item.confidence or 0.0), 0.9),
    )
    sheet_dir = runtime.context_repository._sheet_directory(sheet.kind)
    sheet_ref = f"{sheet_dir}/{sheet.slug}"
    updated_pending = runtime.update_pending_context_item(
        pending_item.id,
        status="promoted",
        metadata={
            "promoted_ref": sheet_ref,
            "promoted_kind": promoted_kind,
            "review_note": _clean_text(note),
        },
        session_id=session_id or pending_item.session_id,
    )
    event = runtime.append_context_event(
        event_type="context.pending.promoted",
        summary=f"Promoted pending {pending_item.capture_kind}: {promoted_title}",
        payload={
            "pending_id": pending_item.id,
            "pending_ref": f"pending/{pending_item.id}",
            "sheet_ref": sheet_ref,
            "promoted_kind": promoted_kind,
            "title": promoted_title,
            "note": _clean_text(note),
        },
        source=pending_item.source,
        entity_refs=[f"pending/{pending_item.id}", sheet_ref],
        session_id=session_id or pending_item.session_id,
    )
    return {
        "ok": True,
        "output": {
            "pending_item": updated_pending.to_dict() if updated_pending else pending_item.to_dict(),
            "sheet": sheet.to_dict(),
            "event": event.to_dict(),
        },
        "error": None,
    }


def defer_pending_context(
    pending_id: str,
    defer_until: str = "",
    defer_for_days: int | None = None,
    note: str = "",
    session_id: str = "",
) -> dict:
    """Defer a pending item so it falls out of the review queue until later."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    pending_item = runtime.get_pending_context_item(pending_id)
    if not pending_item:
        return {"ok": False, "output": "", "error": "pending item not found"}

    pending_data = pending_item.to_dict()
    deferred_until = _defer_until_value(defer_until=defer_until, defer_for_days=defer_for_days)
    metadata = dict(pending_data.get("metadata") or {})
    if deferred_until:
        metadata["defer_until"] = deferred_until
    if note:
        metadata["defer_note"] = note

    updated_pending = runtime.update_pending_context_item(
        pending_item.id,
        status="deferred",
        metadata=metadata,
        session_id=session_id or pending_item.session_id,
    )
    event = runtime.append_context_event(
        event_type="context.pending.deferred",
        summary=f"Deferred pending {pending_item.capture_kind}: {pending_item.title}",
        payload={
            "pending_id": pending_item.id,
            "pending_ref": f"pending/{pending_item.id}",
            "defer_until": deferred_until,
            "note": _clean_text(note),
        },
        source=pending_item.source,
        entity_refs=[f"pending/{pending_item.id}"],
        session_id=session_id or pending_item.session_id,
    )
    return {
        "ok": True,
        "output": {
            "pending_item": updated_pending.to_dict() if updated_pending else pending_item.to_dict(),
            "event": event.to_dict(),
        },
        "error": None,
    }


def dismiss_pending_context(
    pending_id: str,
    note: str = "",
    session_id: str = "",
) -> dict:
    """Dismiss a pending item from the review queue."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    pending_item = runtime.get_pending_context_item(pending_id)
    if not pending_item:
        return {"ok": False, "output": "", "error": "pending item not found"}

    pending_data = pending_item.to_dict()
    metadata = dict(pending_data.get("metadata") or {})
    if note:
        metadata["dismiss_note"] = note

    updated_pending = runtime.update_pending_context_item(
        pending_item.id,
        status="dismissed",
        metadata=metadata,
        session_id=session_id or pending_item.session_id,
    )
    event = runtime.append_context_event(
        event_type="context.pending.dismissed",
        summary=f"Dismissed pending {pending_item.capture_kind}: {pending_item.title}",
        payload={
            "pending_id": pending_item.id,
            "pending_ref": f"pending/{pending_item.id}",
            "note": _clean_text(note),
        },
        source=pending_item.source,
        entity_refs=[f"pending/{pending_item.id}"],
        session_id=session_id or pending_item.session_id,
    )
    return {
        "ok": True,
        "output": {
            "pending_item": updated_pending.to_dict() if updated_pending else pending_item.to_dict(),
            "event": event.to_dict(),
        },
        "error": None,
    }


def restore_pending_context(
    pending_id: str,
    note: str = "",
    session_id: str = "",
) -> dict:
    """Restore a deferred or dismissed pending item back into the active review lane."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    pending_item = runtime.get_pending_context_item(pending_id)
    if not pending_item:
        return {"ok": False, "output": "", "error": "pending item not found"}

    pending_data = pending_item.to_dict()
    metadata = dict(pending_data.get("metadata") or {})
    previous_status = _clean_text(str(pending_data.get("status") or "pending")) or "pending"
    metadata["defer_until"] = ""
    metadata["deferred_until"] = ""
    metadata["restored_from_status"] = previous_status
    if note:
        metadata["restore_note"] = note

    updated_pending = runtime.update_pending_context_item(
        pending_item.id,
        status="pending",
        metadata=metadata,
        session_id=session_id or pending_item.session_id,
    )
    event = runtime.append_context_event(
        event_type="context.pending.restored",
        summary=f"Restored pending {pending_item.capture_kind}: {pending_item.title}",
        payload={
            "pending_id": pending_item.id,
            "pending_ref": f"pending/{pending_item.id}",
            "previous_status": previous_status,
            "note": _clean_text(note),
        },
        source=pending_item.source,
        entity_refs=[f"pending/{pending_item.id}"],
        session_id=session_id or pending_item.session_id,
    )
    return {
        "ok": True,
        "output": {
            "pending_item": updated_pending.to_dict() if updated_pending else pending_item.to_dict(),
            "event": event.to_dict(),
        },
        "error": None,
    }


def list_context_sheets(kind: str = "", limit: int = 10) -> dict:
    """List canonical context sheets."""
    runtime = _get_runtime()
    sheets = [sheet.to_dict() for sheet in runtime.list_context_sheets(kind=kind or None, limit=limit)]
    return {
        "ok": True,
        "output": sheets,
        "error": None,
    }


def context_activity_feed(limit: int = 25) -> dict:
    """Return a LIFO context journal with pinned refs floating to the top."""
    runtime = _get_runtime()
    runtime.init_context_repo()
    pins = _load_pins(runtime)
    events = runtime.list_context_events(limit=max(limit * 4, 40))

    items = [_event_feed_item(runtime, event, pins) for event in events]
    seen_keys = {f"event::{item['id']}" for item in items}
    seen_refs = {_clean_text(str(item.get("ref", ""))) for item in items if _clean_text(str(item.get("ref", "")))}

    for ref, pin_record in pins.items():
        snapshot = _pin_feed_item(runtime, pin_record)
        key = f"pin::{ref}"
        if key in seen_keys or ref in seen_refs:
            continue
        items.append(snapshot)
        seen_keys.add(key)

    items.sort(
        key=lambda item: (
            0 if item.get("pinned") else 1,
            str(item.get("updated_at") or item.get("created_at") or ""),
        ),
        reverse=False,
    )
    # After the pinned-first group key, newest items should be first.
    pinned = [item for item in items if item.get("pinned")]
    pinned.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    regular = [item for item in items if not item.get("pinned")]
    regular.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return {
        "ok": True,
        "output": (pinned + regular)[:limit],
        "error": None,
    }


def pin_context_ref(
    ref: str,
    pinned: bool = True,
    label: str = "",
    note: str = "",
    session_id: str = "",
) -> dict:
    """Pin or unpin a context ref so it stays at the top of the journal/feed."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    normalized_ref = _clean_text(ref)
    if not normalized_ref:
        return {"ok": False, "output": "", "error": "ref is required"}

    pins = _load_pins(runtime)
    snapshot = _load_ref_snapshot(runtime, normalized_ref)
    if pinned:
        pins[normalized_ref] = {
            "ref": normalized_ref,
            "label": _clean_text(label) or _clean_text(snapshot.get("title")) or normalized_ref,
            "note": _clean_text(note),
            "kind": _clean_text(snapshot.get("kind")),
            "path": _clean_text(snapshot.get("path")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        pins.pop(normalized_ref, None)

    path = _save_pins(runtime, pins)
    event = runtime.append_context_event(
        event_type="context.pin.updated",
        summary=f"{'Pinned' if pinned else 'Unpinned'} {normalized_ref}",
        payload={
            "ref": normalized_ref,
            "pinned": pinned,
            "label": _clean_text(label),
            "note": _clean_text(note),
            "pins_path": str(path),
        },
        entity_refs=[normalized_ref],
        session_id=_clean_text(session_id) or None,
    )
    return {
        "ok": True,
        "output": {
            "ref": normalized_ref,
            "pinned": pinned,
            "pins_path": str(path),
            "event": event.to_dict(),
        },
        "error": None,
    }


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        expanded = path.expanduser()
        key = str(expanded)
        if key in seen:
            continue
        seen.add(key)
        unique.append(expanded)
    return unique


def _openscreen_recordings_dir_candidates() -> list[Path]:
    env_path = _clean_text(os.environ.get("AIBUTLER_OPENSCREEN_RECORDINGS_DIR"))
    app_support = Path.home() / "Library" / "Application Support"
    candidates = [
        Path(env_path) if env_path else None,
        app_support / "Openscreen" / "recordings",
        app_support / "OpenScreen" / "recordings",
        app_support / "openscreen" / "recordings",
    ]
    return _unique_paths([path for path in candidates if path is not None])


def _openscreen_app_candidates() -> list[Path]:
    env_path = _clean_text(os.environ.get("AIBUTLER_OPENSCREEN_APP_PATH"))
    candidates = [
        Path(env_path) if env_path else None,
        Path("/Applications/Openscreen.app"),
        Path("/Applications/OpenScreen.app"),
        Path.home() / "Applications" / "Openscreen.app",
        Path.home() / "Applications" / "OpenScreen.app",
    ]
    return _unique_paths([path for path in candidates if path is not None])


def _openscreen_repo_candidates() -> list[Path]:
    env_path = _clean_text(os.environ.get("AIBUTLER_OPENSCREEN_REPO"))
    candidates = [
        Path(env_path) if env_path else None,
        Path.home() / "Documents" / "Coding" / "App Development and Coding" / "Claw-Code" / "openscreen",
    ]
    return _unique_paths([path for path in candidates if path is not None])


def _detect_openscreen_recordings_dir() -> Path | None:
    for candidate in _openscreen_recordings_dir_candidates():
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _detect_openscreen_app() -> Path | None:
    for candidate in _openscreen_app_candidates():
        if candidate.exists():
            return candidate
    return None


def _detect_openscreen_repo() -> Path | None:
    for candidate in _openscreen_repo_candidates():
        if candidate.exists() and (candidate / "package.json").exists():
            return candidate
    return None


def _normalize_openscreen_created_at(value: Any, fallback: datetime | None = None) -> str:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(value, str) and _clean_text(value):
        return _clean_text(value)
    return (fallback or datetime.now(timezone.utc)).isoformat()


def _path_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "byte_size": 0,
            "modified_at": None,
        }

    resolved = path.expanduser()
    try:
        stat = resolved.stat()
    except OSError:
        return {
            "path": str(resolved),
            "exists": False,
            "byte_size": 0,
            "modified_at": None,
        }

    return {
        "path": str(resolved),
        "exists": True,
        "byte_size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _count_cursor_samples(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    samples = payload.get("samples")
    return len(samples) if isinstance(samples, list) else 0


def _humanize_session_title(stem: str) -> str:
    normalized = re.sub(r"[_-]+", " ", stem).strip()
    return normalized.title() if normalized else "OpenScreen Capture"


def _read_openscreen_session_record(manifest_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    screen_video_path = _clean_text(str(payload.get("screenVideoPath") or ""))
    webcam_video_path = _clean_text(str(payload.get("webcamVideoPath") or ""))
    if not screen_video_path:
        return None

    manifest_snapshot = _path_snapshot(manifest_path)
    screen_path = Path(screen_video_path).expanduser()
    webcam_path = Path(webcam_video_path).expanduser() if webcam_video_path else None
    cursor_path = Path(f"{screen_path}.cursor.json")
    stem = manifest_path.name.removesuffix(".session.json")
    recorded_at = _normalize_openscreen_created_at(
        payload.get("createdAt"),
        fallback=datetime.fromisoformat(manifest_snapshot["modified_at"]) if manifest_snapshot.get("modified_at") else None,
    )

    return {
        "id": stem,
        "title": _humanize_session_title(stem),
        "recorded_at": recorded_at,
        "session_manifest_path": str(manifest_path),
        "screen_video": _path_snapshot(screen_path),
        "webcam_video": _path_snapshot(webcam_path),
        "cursor_telemetry": {
            **_path_snapshot(cursor_path),
            "sample_count": _count_cursor_samples(cursor_path),
        },
        "manifest": manifest_snapshot,
    }


def _list_openscreen_session_records(limit: int = 10) -> tuple[Path | None, list[dict[str, Any]]]:
    recordings_dir = _detect_openscreen_recordings_dir()
    if recordings_dir is None:
        return None, []

    manifests = sorted(
        recordings_dir.glob("*.session.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    sessions: list[dict[str, Any]] = []
    for manifest_path in manifests:
        record = _read_openscreen_session_record(manifest_path)
        if record:
            sessions.append(record)
        if len(sessions) >= max(limit, 0):
            break
    return recordings_dir, sessions


def openscreen_status() -> dict:
    """Return Butler's current OpenScreen integration status."""
    recordings_dir, sessions = _list_openscreen_session_records(limit=3)
    repo_path = _detect_openscreen_repo()
    app_path = _detect_openscreen_app()
    repo_ready = bool(repo_path and (repo_path / "node_modules").exists())
    return {
        "ok": True,
        "output": {
            "available": bool(recordings_dir or repo_path or app_path),
            "app_bundle_path": str(app_path) if app_path else None,
            "repo_path": str(repo_path) if repo_path else None,
            "repo_ready": repo_ready,
            "recordings_dir": str(recordings_dir) if recordings_dir else None,
            "session_count": len(sessions),
            "latest_session": sessions[0] if sessions else None,
            "candidate_recordings_dirs": [str(path) for path in _openscreen_recordings_dir_candidates()],
        },
        "error": None,
    }


def openscreen_list_sessions(limit: int = 10) -> dict:
    """List recent OpenScreen recording sessions discovered on this Mac."""
    recordings_dir, sessions = _list_openscreen_session_records(limit=limit)
    return {
        "ok": True,
        "output": {
            "recordings_dir": str(recordings_dir) if recordings_dir else None,
            "sessions": sessions,
        },
        "error": None,
    }


def openscreen_launch(launch_mode: str = "auto") -> dict:
    """Launch OpenScreen from an installed app bundle or a local dev checkout."""
    runtime = _get_runtime()
    normalized_mode = _clean_text(launch_mode).lower() or "auto"
    if normalized_mode not in {"auto", "app", "repo"}:
        return {
            "ok": False,
            "output": "",
            "error": "launch_mode must be one of: auto, app, repo",
        }

    app_path = _detect_openscreen_app()
    repo_path = _detect_openscreen_repo()

    if normalized_mode in {"auto", "app"} and app_path:
        result = subprocess.run(["open", str(app_path)], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return {
                "ok": True,
                "output": {
                    "launched_via": "app",
                    "app_bundle_path": str(app_path),
                },
                "error": None,
            }
        return {
            "ok": False,
            "output": "",
            "error": result.stderr.strip() or f"Failed to open {app_path}",
        }

    if normalized_mode in {"auto", "repo"} and repo_path:
        if not (repo_path / "node_modules").exists():
            return {
                "ok": False,
                "output": {
                    "repo_path": str(repo_path),
                    "next_step": "Install OpenScreen dependencies in the repo before launching dev mode.",
                },
                "error": "OpenScreen repo was found, but node_modules is missing.",
            }

        log_dir = runtime.base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "openscreen-dev.log"
        with log_path.open("ab") as log_handle:
            subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=repo_path,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return {
            "ok": True,
            "output": {
                "launched_via": "repo",
                "repo_path": str(repo_path),
                "log_path": str(log_path),
            },
            "error": None,
        }

    return {
        "ok": False,
        "output": {
            "app_bundle_path": str(app_path) if app_path else None,
            "repo_path": str(repo_path) if repo_path else None,
        },
        "error": "OpenScreen was not found as an installed app or a launchable local repo.",
    }


def openscreen_import_session(
    session_manifest_path: str = "",
    pin: bool = False,
    session_id: str = "",
) -> dict:
    """Link an OpenScreen recording session into Butler context without copying the media."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    manifest_path = Path(_clean_text(session_manifest_path)).expanduser() if _clean_text(session_manifest_path) else None
    if manifest_path is None:
        _, sessions = _list_openscreen_session_records(limit=1)
        record = sessions[0] if sessions else None
    else:
        record = _read_openscreen_session_record(manifest_path)

    if not record:
        return {
            "ok": False,
            "output": "",
            "error": "No OpenScreen session could be found to import.",
        }

    if not record["screen_video"].get("exists"):
        return {
            "ok": False,
            "output": "",
            "error": "The selected OpenScreen session is missing its screen video file.",
        }

    artifact_slug = _slugify(f"openscreen-{record['id']}")
    artifact_path = runtime.context_repository.base_dir / "artifacts" / f"{artifact_slug}.md"
    artifact_exists = artifact_path.exists()
    artifact_ref = f"artifacts/{artifact_slug}"

    metadata = {
        "source_app": "OpenScreen",
        "capture_type": "screen_recording",
        "import_mode": "linked",
        "recorded_at": record["recorded_at"],
        "session_manifest_path": record["session_manifest_path"],
        "screen_video_path": record["screen_video"]["path"],
        "screen_video_size_bytes": record["screen_video"]["byte_size"],
        "webcam_video_path": record["webcam_video"]["path"],
        "webcam_video_size_bytes": record["webcam_video"]["byte_size"],
        "cursor_telemetry_path": record["cursor_telemetry"]["path"],
        "cursor_sample_count": record["cursor_telemetry"]["sample_count"],
    }
    body_lines = [
        "Linked OpenScreen capture. The media stays in OpenScreen storage and Butler references it without copying the large files.",
        "",
        f"- Recorded at: `{record['recorded_at']}`",
        f"- Session manifest: `{record['session_manifest_path']}`",
        f"- Screen video: `{record['screen_video']['path']}`",
    ]
    if record["webcam_video"].get("path"):
        body_lines.append(f"- Webcam video: `{record['webcam_video']['path']}`")
    if record["cursor_telemetry"].get("path"):
        body_lines.append(f"- Cursor telemetry: `{record['cursor_telemetry']['path']}`")
    if record["cursor_telemetry"].get("sample_count"):
        body_lines.append(f"- Cursor samples: `{record['cursor_telemetry']['sample_count']}`")

    sheet = runtime.create_context_sheet(
        kind="artifact",
        name=record["title"],
        slug=artifact_slug,
        body="\n".join(body_lines),
        metadata=metadata,
        source_refs=[record["session_manifest_path"], record["screen_video"]["path"]],
        confidence=0.92,
    )

    pending_item = None
    if not artifact_exists:
        pending_item = runtime.capture_pending_context(
            capture_kind="screen-recording",
            title=f"Review OpenScreen capture: {record['title']}",
            content=(
                "This capture is linked into Butler. Add people, place, project, and follow-up context if it matters."
            ),
            metadata={
                "artifact_ref": artifact_ref,
                "session_manifest_path": record["session_manifest_path"],
            },
            source={
                "app": "OpenScreen",
                "surface": "desktop-capture",
                "device": "mac",
            },
            confidence=0.35,
            session_id=_clean_text(session_id) or None,
        )

    event_refs = [artifact_ref]
    if pending_item:
        event_refs.append(f"pending/{pending_item.id}")
    event = runtime.append_context_event(
        event_type="context.openscreen.imported",
        summary=f"Imported OpenScreen capture {record['title']}",
        payload={
            "artifact_ref": artifact_ref,
            "session_manifest_path": record["session_manifest_path"],
            "screen_video_path": record["screen_video"]["path"],
            "linked_only": True,
            "pending_id": pending_item.id if pending_item else None,
        },
        source={
            "app": "OpenScreen",
            "surface": "desktop-capture",
            "device": "mac",
        },
        entity_refs=event_refs,
        session_id=_clean_text(session_id) or None,
    )

    if pin:
        pins = _load_pins(runtime)
        pins[artifact_ref] = {
            "ref": artifact_ref,
            "label": record["title"],
            "note": "Imported from OpenScreen",
            "kind": "artifact",
            "path": sheet.path,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_pins(runtime, pins)

    return {
        "ok": True,
        "output": {
            "artifact_sheet": sheet.to_dict(),
            "artifact_ref": artifact_ref,
            "pending_item": pending_item.to_dict() if pending_item else None,
            "provenance_event": event.to_dict(),
            "linked_only": True,
        },
        "error": None,
    }


def butler_memory_status() -> dict:
    """Return the status of Butler's MemPalace-style recall index."""
    index = _get_mempalace_index()
    return {
        "ok": True,
        "output": index.status(),
        "error": None,
    }


def butler_memory_index(
    include_sheets: bool = True,
    include_pending: bool = True,
    include_events: bool = True,
    clear: bool = False,
) -> dict:
    """Project Butler context into a local MemPalace-compatible recall index."""
    runtime = _get_runtime()
    runtime.init_context_repo()
    index = _get_mempalace_index()
    output = index.index_context(
        include_sheets=include_sheets,
        include_pending=include_pending,
        include_events=include_events,
        clear=clear,
    )
    return {
        "ok": True,
        "output": output,
        "error": None,
    }


def butler_memory_search(
    query: str,
    limit: int = 5,
    wing: str = "",
    room: str = "",
) -> dict:
    """Search Butler context through the MemPalace-style recall layer."""
    runtime = _get_runtime()
    runtime.init_context_repo()
    index = _get_mempalace_index()
    bootstrapped = False
    if _clean_text(query) and index.count() == 0:
        index.index_context()
        bootstrapped = True
    output = index.query(
        query=query,
        limit=limit,
        wing=_clean_text(wing) or None,
        room=_clean_text(room) or None,
    )
    output["bootstrapped"] = bootstrapped
    return {
        "ok": True,
        "output": output,
        "error": None,
    }


TOOLS = {
    "capture_pending_context": {
        "fn": capture_pending_context,
        "description": "Capture an unresolved receipt, note, contact, or other item into the pending context queue.",
        "params": {
            "capture_kind": "str",
            "title": "str",
            "content": "str=",
            "confidence": "float=0.0",
            "source_app": "str=",
            "source_device": "str=",
            "source_hardware": "str=",
            "source_surface": "str=",
            "place_ref": "str=",
            "session_id": "str=",
        },
    },
    "capture_context_artifact": {
        "fn": capture_context_artifact,
        "description": "Persist a phone photo or attachment into the context inbox, then create a pending review item with provenance.",
        "params": {
            "capture_kind": "str",
            "title": "str",
            "content": "str=",
            "file_name": "str=",
            "mime_type": "str=",
            "data_base64": "str=",
            "source_app": "str=",
            "source_device": "str=",
            "source_hardware": "str=",
            "source_surface": "str=",
            "place_ref": "str=",
            "session_id": "str=",
        },
    },
    "list_pending_context": {
        "fn": list_pending_context,
        "description": "List the latest pending context items awaiting human review.",
        "params": {
            "limit": "int=10",
        },
    },
    "context_review_queue": {
        "fn": context_review_queue,
        "description": "Return a combined review queue for pending context items and relationship follow-ups.",
        "params": {
            "limit": "int=20",
            "include_relationships": "bool=True",
        },
    },
    "promote_pending_context": {
        "fn": promote_pending_context,
        "description": "Promote a pending context item into a canonical sheet and mark it reviewed.",
        "params": {
            "pending_id": "str",
            "kind": "str=''",
            "title": "str=''",
            "note": "str=''",
            "session_id": "str=''",
        },
    },
    "defer_pending_context": {
        "fn": defer_pending_context,
        "description": "Defer a pending context item so it falls out of the review queue until later.",
        "params": {
            "pending_id": "str",
            "defer_until": "str=''",
            "defer_for_days": "int=",
            "note": "str=''",
            "session_id": "str=''",
        },
    },
    "dismiss_pending_context": {
        "fn": dismiss_pending_context,
        "description": "Dismiss a pending context item from the review queue.",
        "params": {
            "pending_id": "str",
            "note": "str=''",
            "session_id": "str=''",
        },
    },
    "restore_pending_context": {
        "fn": restore_pending_context,
        "description": "Restore a deferred or dismissed pending context item back into the active review queue.",
        "params": {
            "pending_id": "str",
            "note": "str=''",
            "session_id": "str=''",
        },
    },
    "list_context_sheets": {
        "fn": list_context_sheets,
        "description": "List canonical context sheets such as people, places, and artifacts.",
        "params": {
            "kind": "str=",
            "limit": "int=10",
        },
    },
    "context_activity_feed": {
        "fn": context_activity_feed,
        "description": "Return a LIFO journal-style activity feed built from context events, with pinned refs at the top.",
        "params": {
            "limit": "int=25",
        },
    },
    "context_graph_snapshot": {
        "fn": context_graph_snapshot,
        "description": "Return a relationship-first context graph snapshot for rich mobile and desktop review surfaces.",
        "params": {
            "relationship_limit": "int=6",
            "pending_limit": "int=4",
            "signal_limit": "int=5",
            "pin_limit": "int=4",
        },
    },
    "pin_context_ref": {
        "fn": pin_context_ref,
        "description": "Pin or unpin a context ref so it stays prominent in the journal and review surfaces.",
        "params": {
            "ref": "str",
            "pinned": "bool=True",
            "label": "str=",
            "note": "str=",
            "session_id": "str=",
        },
    },
    "openscreen_status": {
        "fn": openscreen_status,
        "description": "Inspect whether OpenScreen is available on this Mac and summarize its latest capture session.",
        "params": {},
    },
    "openscreen_list_sessions": {
        "fn": openscreen_list_sessions,
        "description": "List recent OpenScreen recording sessions discovered in the local recordings directory.",
        "params": {
            "limit": "int=10",
        },
    },
    "openscreen_launch": {
        "fn": openscreen_launch,
        "description": "Launch OpenScreen from an installed app bundle or a local dev checkout.",
        "params": {
            "launch_mode": "str=auto",
        },
    },
    "openscreen_import_session": {
        "fn": openscreen_import_session,
        "description": "Link an OpenScreen recording session into Butler context without duplicating the large media files.",
        "params": {
            "session_manifest_path": "str=",
            "pin": "bool=False",
            "session_id": "str=",
        },
    },
    "butler_memory_status": {
        "fn": butler_memory_status,
        "description": "Inspect Butler's local MemPalace-style recall index and show wing/room counts.",
        "params": {},
    },
    "butler_memory_index": {
        "fn": butler_memory_index,
        "description": "Index Butler's canonical context repo into a local MemPalace-compatible recall layer.",
        "params": {
            "include_sheets": "bool=True",
            "include_pending": "bool=True",
            "include_events": "bool=True",
            "clear": "bool=False",
        },
    },
    "butler_memory_search": {
        "fn": butler_memory_search,
        "description": "Semantic search over Butler context using the MemPalace-style local recall index.",
        "params": {
            "query": "str",
            "limit": "int=5",
            "wing": "str=",
            "room": "str=",
        },
    },
}
