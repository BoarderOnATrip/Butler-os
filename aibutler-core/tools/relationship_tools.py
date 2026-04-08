#!/usr/bin/env python3
"""
aiButler relationship tools.

These tools turn canonical person sheets plus append-only events into a usable
CRM spine: interaction ingest, durable person records, and a follow-up queue.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from runtime.context_repository import slugify
from runtime.models import utc_now
from tools.life_data import contacts_list, contacts_search


def _get_runtime():
    from runtime.engine import get_default_runtime

    return get_default_runtime()


def _clean_text(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if cleaned.lower() == "missing value":
        return ""
    return cleaned


def _clean_lower(value: str | None) -> str:
    return _clean_text(value).lower()


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        value = _clean_text(raw)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _parse_tags(tags_csv: str = "") -> list[str]:
    return _dedupe_strings([part for part in tags_csv.split(",") if part])


def _parse_datetime(value: str | None) -> datetime | None:
    raw = _clean_text(value)
    if not raw:
        return None
    if raw.lower() == "today":
        return datetime.now(timezone.utc).replace(hour=17, minute=0, second=0, microsecond=0)
    if raw.lower() == "tomorrow":
        return (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)

    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        raw = f"{raw}T17:00:00+00:00"
    elif raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_due_at(
    next_action_due_at: str = "",
    follow_up_in_days: int | None = None,
    due_date: str = "",
) -> str | None:
    for candidate in (next_action_due_at, due_date):
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed.isoformat()

    if follow_up_in_days is not None:
        try:
            days = int(follow_up_in_days)
        except (TypeError, ValueError):
            return None
        return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
            hour=17,
            minute=0,
            second=0,
            microsecond=0,
        ).isoformat()

    return None


def _priority_base(priority: str) -> int:
    return {
        "critical": 100,
        "high": 80,
        "medium": 55,
        "low": 25,
    }.get(_clean_lower(priority), 40)


def _stage_bonus(stage: str) -> int:
    return {
        "replied": 24,
        "qualified": 18,
        "contacted": 14,
        "warm": 12,
        "active": 10,
        "new": 8,
    }.get(_clean_lower(stage), 4)


def _timing_bonus(due_at: str | None) -> tuple[int, bool]:
    parsed = _parse_datetime(due_at)
    if not parsed:
        return 0, False

    now = datetime.now(timezone.utc)
    if parsed <= now:
        overdue_days = max(1, int((now - parsed).total_seconds() // 86400) + 1)
        return min(45, 20 + overdue_days * 8), True
    if parsed <= now + timedelta(hours=24):
        return 16, False
    if parsed <= now + timedelta(days=3):
        return 8, False
    return 0, False


def _touch_staleness_bonus(last_touch_at: str | None) -> int:
    touched = _parse_datetime(last_touch_at)
    if not touched:
        return 8
    days_since = (datetime.now(timezone.utc) - touched).days
    if days_since >= 14:
        return 12
    if days_since >= 7:
        return 8
    if days_since >= 3:
        return 4
    return 0


def _format_due_label(value: str | None) -> str:
    parsed = _parse_datetime(value)
    if not parsed:
        return "No due date"
    now = datetime.now(timezone.utc)
    day_delta = (parsed.date() - now.date()).days
    if parsed < now and day_delta <= 0:
        overdue_days = max(1, abs(day_delta))
        return f"Overdue by {overdue_days}d"
    if day_delta == 0:
        return "Due today"
    if day_delta == 1:
        return "Due tomorrow"
    return f"Due in {day_delta}d"


def _build_source(
    *,
    source_app: str = "",
    source_device: str = "",
    source_hardware: str = "",
    source_surface: str = "",
) -> dict[str, str]:
    source = {
        "app": _clean_text(source_app),
        "device": _clean_text(source_device),
        "hardware": _clean_text(source_hardware),
        "surface": _clean_text(source_surface),
    }
    return {key: value for key, value in source.items() if value}


def _clean_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: nested
        for key, nested in value.items()
        if nested not in ("", None, [], {})
    }


def _merge_preferred(
    existing: str | None,
    incoming: str | None,
    *,
    fallback: str = "",
) -> str:
    if _clean_text(incoming):
        return _clean_text(incoming)
    if _clean_text(existing):
        return _clean_text(existing)
    return fallback


def _humanize_slug(value: str) -> str:
    raw = _clean_text(value).replace("-", " ").replace("_", " ")
    return " ".join(part for part in raw.split() if part).title()


def _context_ref_prefix(kind: str) -> str:
    return {
        "organization": "organizations",
        "place": "places",
        "conversation": "conversations",
    }.get(_clean_lower(kind), f"{_clean_lower(kind)}s")


def _canonical_context_ref(kind: str, ref: str = "", name: str = "") -> tuple[str, str, str]:
    normalized_kind = _clean_lower(kind)
    normalized_ref = _clean_text(ref)
    normalized_name = _clean_text(name)
    slug_source = ""
    if normalized_ref:
        slug_source = normalized_ref.rsplit("/", 1)[-1]
    if not slug_source:
        slug_source = normalized_name
    slug = slugify(slug_source or normalized_kind)
    canonical_ref = f"{_context_ref_prefix(normalized_kind)}/{slug}"
    display_name = normalized_name or _humanize_slug(slug_source or slug)
    return canonical_ref, slug, display_name


def _linked_context_path(runtime, kind: str, slug: str):
    return runtime.context_repository.base_dir / _context_ref_prefix(kind) / f"{slug}.md"


def _format_linked_context_line(label: str, name: str = "", ref: str = "") -> str | None:
    normalized_name = _clean_text(name)
    normalized_ref = _clean_text(ref)
    if not normalized_name and not normalized_ref:
        return None
    if normalized_name and normalized_ref:
        return f"- {label}: {normalized_name} ({normalized_ref})"
    return f"- {label}: {normalized_name or normalized_ref}"


def _generate_linked_context_body(
    *,
    title: str,
    kind_label: str,
    person_name: str,
    person_ref: str,
    channel: str = "",
    direction: str = "",
    summary: str = "",
    extra_lines: list[str] | None = None,
) -> str:
    lines = [f"# {title}", "", f"## {kind_label}"]
    for entry in (
        _format_linked_context_line("Linked person", person_name, person_ref),
        _format_linked_context_line("Channel", channel),
        _format_linked_context_line("Direction", direction),
    ):
        if entry:
            lines.append(entry)
    if summary:
        lines.extend(["", "## Latest Interaction", summary])
    if extra_lines:
        filtered = [line for line in extra_lines if _clean_text(line)]
        if filtered:
            lines.extend(["", "## Details", *filtered])
    return "\n".join(lines).strip()


def _upsert_linked_context_sheet(
    runtime,
    *,
    kind: str,
    title: str,
    ref: str = "",
    person_name: str,
    person_ref: str,
    channel: str = "",
    direction: str = "",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
    extra_lines: list[str] | None = None,
) -> dict[str, Any]:
    canonical_ref, slug, display_name = _canonical_context_ref(kind, ref, title)
    path = _linked_context_path(runtime, kind, slug)
    existing = runtime.context_repository.read_sheet(path) if path.exists() else None

    existing_metadata = dict(existing.metadata or {}) if existing else {}
    existing_links = list(existing.links or []) if existing else []
    existing_source_refs = list(existing.source_refs or []) if existing else []

    merged_metadata = {
        **existing_metadata,
        **{key: value for key, value in (metadata or {}).items() if value not in ("", None, [], {})},
        "linked_person_ref": person_ref,
        "linked_person_name": _clean_text(person_name),
        "last_interaction_channel": _clean_text(channel),
        "last_interaction_direction": _clean_text(direction),
        "last_interaction_summary": _clean_text(summary),
        "context_ref": canonical_ref,
    }

    if _clean_text(title):
        merged_metadata["title"] = _clean_text(title)

    if kind == "organization":
        merged_metadata["organization_ref"] = canonical_ref
        merged_metadata["organization_name"] = display_name
    elif kind == "place":
        merged_metadata["place_ref"] = canonical_ref
        merged_metadata["place_name"] = display_name
    elif kind == "conversation":
        merged_metadata["conversation_ref"] = canonical_ref
        merged_metadata["conversation_label"] = display_name

    merged_links = _dedupe_strings(existing_links + [person_ref])
    merged_source_refs = _dedupe_strings(existing_source_refs + [person_ref])
    body = _generate_linked_context_body(
        title=display_name,
        kind_label=kind.title(),
        person_name=person_name,
        person_ref=person_ref,
        channel=channel,
        direction=direction,
        summary=summary,
        extra_lines=extra_lines,
    )

    sheet = runtime.create_context_sheet(
        kind=kind,
        name=display_name,
        slug=slug,
        body=body if body else (existing.body if existing else ""),
        links=merged_links,
        source_refs=merged_source_refs,
        metadata=merged_metadata,
        status=existing.status if existing else "active",
        confidence=max(existing.confidence if existing else 0.0, 0.9 if body else 0.8),
    )

    return {
        "ref": canonical_ref,
        "name": sheet.name,
        "sheet": sheet,
    }


def _merge_person_links(existing_links: list[str], linked_refs: list[str]) -> list[str]:
    return _dedupe_strings(list(existing_links) + linked_refs)


def _load_pins(runtime) -> set[str]:
    path = runtime.context_repository.base_dir / "indexes" / "pins.json"
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, list):
        return set()
    return {
        str(item.get("ref"))
        for item in payload
        if isinstance(item, dict) and item.get("ref")
    }


def _parse_contact_line(raw: str) -> dict[str, str]:
    parts = [part.strip() for part in raw.split("|")]
    return {
        "full_name": parts[0] if len(parts) > 0 else "",
        "phone": parts[1] if len(parts) > 1 else "",
        "email": parts[2] if len(parts) > 2 else "",
    }


def _maybe_enrich_from_contacts(person_name: str) -> dict[str, str]:
    if not _clean_text(person_name):
        return {}
    result = contacts_search(person_name)
    if not result.get("ok"):
        return {}

    rows = [_parse_contact_line(str(row)) for row in result.get("output", [])]
    exact = [row for row in rows if _clean_lower(row.get("full_name")) == _clean_lower(person_name)]
    candidates = exact or rows
    if len(candidates) != 1:
        return {}
    candidate = candidates[0]
    return {
        "full_name": _clean_text(candidate.get("full_name")),
        "phone": _clean_text(candidate.get("phone")),
        "email": _clean_text(candidate.get("email")),
    }


def _find_person_sheet(runtime, *, person_name: str, phone: str = "", email: str = ""):
    people = runtime.context_repository.list_sheets(kind="person", limit=500)
    target_slug = slugify(person_name)
    target_name = _clean_lower(person_name)
    target_phone = _clean_text(phone)
    target_email = _clean_lower(email)

    exact_slug = next((sheet for sheet in people if sheet.slug == target_slug), None)
    if exact_slug:
        return exact_slug

    for sheet in people:
        metadata = dict(sheet.metadata or {})
        contact = dict(metadata.get("contact") or {})
        if target_phone and _clean_text(contact.get("phone")) == target_phone:
            return sheet
        if target_email and _clean_lower(contact.get("email")) == target_email:
            return sheet
        if _clean_lower(sheet.name) == target_name:
            return sheet
    return None


def _generate_person_body(
    *,
    name: str,
    company: str,
    role: str,
    relationship_type: str,
    priority: str,
    stage: str,
    channel: str,
    summary: str,
    next_action: str,
    next_action_due_at: str | None,
    open_loop: str,
    notes: str,
    phone: str,
    email: str,
    tags: list[str],
    organization_ref: str = "",
    organization_name: str = "",
    place_ref: str = "",
    place_name: str = "",
    conversation_ref: str = "",
    conversation_label: str = "",
) -> str:
    lines = [f"# {name}", ""]

    headline_parts = [part for part in (role, company) if part]
    if headline_parts:
        lines.append(" | ".join(headline_parts))
        lines.append("")

    lines.extend(
        [
            "## Relationship",
            f"- Type: {relationship_type or 'contact'}",
            f"- Priority: {priority or 'medium'}",
            f"- Stage: {stage or 'active'}",
            f"- Preferred channel: {channel or 'unknown'}",
        ]
    )
    if phone:
        lines.append(f"- Phone: {phone}")
    if email:
        lines.append(f"- Email: {email}")
    if tags:
        lines.append(f"- Tags: {', '.join(tags)}")
    lines.append("")

    linked_context_lines = [
        _format_linked_context_line("Organization", organization_name, organization_ref),
        _format_linked_context_line("Place", place_name, place_ref),
        _format_linked_context_line("Conversation", conversation_label, conversation_ref),
    ]
    linked_context_lines = [line for line in linked_context_lines if line]
    if linked_context_lines:
        lines.extend(["## Linked Context", *linked_context_lines, ""])

    if summary:
        lines.extend(["## Latest Interaction", summary, ""])
    if open_loop:
        lines.extend(["## Open Loop", open_loop, ""])
    if next_action:
        lines.extend(["## Next Action", next_action])
        if next_action_due_at:
            lines.append(f"Due: {_format_due_label(next_action_due_at)}")
        lines.append("")
    if notes:
        lines.extend(["## Notes", notes, ""])

    return "\n".join(lines).strip()


def _relationship_record_from_sheet(sheet, *, pinned_refs: set[str] | None = None) -> dict[str, Any]:
    metadata = dict(sheet.metadata or {})
    contact = dict(metadata.get("contact") or {})
    relationship = dict(metadata.get("relationship") or {})
    tags = list(metadata.get("tags") or [])
    person_ref = f"people/{sheet.slug}"

    due_at = relationship.get("next_action_due_at")
    score_bonus, overdue = _timing_bonus(due_at)
    score = (
        _priority_base(str(relationship.get("priority", "")))
        + _stage_bonus(str(relationship.get("stage", "")))
        + score_bonus
        + _touch_staleness_bonus(relationship.get("last_touch_at"))
    )

    return {
        "id": sheet.id,
        "person_ref": person_ref,
        "full_name": sheet.name,
        "company": _clean_text(contact.get("company")),
        "role": _clean_text(contact.get("role")),
        "phone": _clean_text(contact.get("phone")),
        "email": _clean_text(contact.get("email")),
        "path": sheet.path,
        "stage": _clean_text(relationship.get("stage")) or "active",
        "priority": _clean_text(relationship.get("priority")) or "medium",
        "channel": _clean_text(relationship.get("preferred_channel")) or "call",
        "relationship_type": _clean_text(relationship.get("relationship_type")) or "contact",
        "owner": _clean_text(relationship.get("owner")) or "Tyler",
        "organization_ref": _clean_text(relationship.get("organization_ref")),
        "organization_name": _clean_text(relationship.get("organization_name")),
        "place_ref": _clean_text(relationship.get("place_ref")),
        "place_name": _clean_text(relationship.get("place_name")),
        "conversation_ref": _clean_text(relationship.get("conversation_ref")),
        "conversation_label": _clean_text(relationship.get("conversation_label")),
        "last_touch_at": relationship.get("last_touch_at"),
        "next_action_due_at": due_at,
        "next_action": _clean_text(relationship.get("next_action")),
        "open_loop": _clean_text(relationship.get("open_loop")),
        "thread_summary": _clean_text(relationship.get("thread_summary")),
        "notes": _clean_text(relationship.get("notes")),
        "tags": tags,
        "interaction_count": int(relationship.get("interaction_count", 0) or 0),
        "score": score,
        "overdue": overdue,
        "due_label": _format_due_label(due_at),
        "pinned": person_ref in (pinned_refs or set()),
        "updated_at": sheet.updated_at,
    }


def _phone_signal_record_id(record: dict[str, Any]) -> str:
    explicit = _clean_text(str(record.get("record_id") or ""))
    if explicit:
        return explicit
    parts = [
        _clean_text(str(record.get("channel") or "")),
        _clean_text(str(record.get("phone") or "")),
        _clean_text(str(record.get("timestamp") or "")),
        _clean_text(str(record.get("thread_id") or "")),
        _clean_text(str(record.get("snippet") or record.get("body") or ""))[:80],
    ]
    return "|".join(part for part in parts if part)


def _existing_phone_signal_ids(runtime, *, limit: int = 4000) -> set[str]:
    ids: set[str] = set()
    for event in runtime.list_context_events(limit=limit):
        if event.event_type not in {"relationship.phone_signal.ingested", "phone.metadata.ingested"}:
            continue
        source_record_id = _clean_text(str(event.payload.get("source_record_id") or ""))
        if not source_record_id:
            phone_metadata = event.payload.get("phone_metadata")
            if isinstance(phone_metadata, dict):
                source_record_id = _clean_text(str(phone_metadata.get("source_record_id") or ""))
        if source_record_id:
            ids.add(source_record_id)
    return ids


def _phone_signal_direction(record: dict[str, Any]) -> str:
    explicit = _clean_lower(record.get("direction"))
    if explicit:
        return explicit

    call_type = _clean_lower(record.get("call_type"))
    sms_type = _clean_lower(record.get("sms_type"))
    if call_type in {"incoming", "missed", "rejected", "blocked", "voicemail"}:
        return "inbound"
    if call_type in {"outgoing"}:
        return "outbound"
    if sms_type in {"inbox", "received"}:
        return "inbound"
    if sms_type in {"sent", "queued", "outbox"}:
        return "outbound"
    return "two-way"


def _phone_signal_summary(record: dict[str, Any]) -> str:
    snippet = _clean_text(str(record.get("summary") or record.get("snippet") or record.get("body") or ""))
    if snippet:
        return snippet

    channel = _clean_lower(record.get("channel")) or "call"
    call_type = _clean_lower(record.get("call_type"))
    if channel == "call":
        if call_type == "missed":
            return "Missed call"
        if call_type == "incoming":
            return "Incoming call"
        if call_type == "outgoing":
            return "Outgoing call"
        if call_type == "voicemail":
            return "Voicemail"
        return "Phone call"
    return "SMS thread activity"


def _phone_signal_next_action(record: dict[str, Any]) -> str:
    explicit = _clean_text(str(record.get("next_action") or ""))
    if explicit:
        return explicit

    channel = _clean_lower(record.get("channel")) or "call"
    direction = _phone_signal_direction(record)
    call_type = _clean_lower(record.get("call_type"))
    if channel == "call" and call_type == "missed":
        return "Return missed call"
    if channel == "text" and direction == "inbound" and _clean_text(str(record.get("snippet") or record.get("body") or "")):
        return "Reply to text thread"
    return ""


def _phone_signal_priority(record: dict[str, Any], next_action: str) -> str:
    explicit = _clean_text(str(record.get("priority") or ""))
    if explicit:
        return explicit
    if next_action:
        return "high"
    return "medium"


def _phone_signal_due_date(record: dict[str, Any], next_action: str) -> str:
    explicit = _clean_text(str(record.get("next_action_due_at") or record.get("due_date") or ""))
    if explicit:
        return explicit
    if not next_action:
        return ""
    channel = _clean_lower(record.get("channel")) or "call"
    if channel == "call":
        return "today"
    return "tomorrow"


def _phone_signal_notes(record: dict[str, Any]) -> str:
    parts: list[str] = []
    timestamp = _clean_text(str(record.get("timestamp") or ""))
    if timestamp:
        parts.append(f"Timestamp: {timestamp}")
    duration = record.get("duration_seconds")
    if duration not in (None, "", 0, "0"):
        parts.append(f"Duration: {duration} seconds")
    thread_id = _clean_text(str(record.get("thread_id") or ""))
    if thread_id:
        parts.append(f"Thread ID: {thread_id}")
    phone = _clean_text(str(record.get("phone") or ""))
    if phone:
        parts.append(f"Phone: {phone}")
    source = _clean_text(str(record.get("source") or "Android phone"))
    parts.append(f"Imported from: {source}")
    return "\n".join(parts)


def _phone_signal_pending_payload(record: dict[str, Any]) -> dict[str, Any]:
    proposed_name = _clean_text(str(record.get("name") or "")) or _clean_text(str(record.get("phone") or "Unknown contact"))
    summary = _phone_signal_summary(record)
    return {
        "review_kind": "relationship_interaction",
        "proposed_record": {
            "person_name": proposed_name,
            "channel": _clean_text(str(record.get("channel") or "call")) or "call",
            "summary": summary,
            "phone": _clean_text(str(record.get("phone") or "")),
            "email": _clean_text(str(record.get("email") or "")),
            "direction": _phone_signal_direction(record),
            "next_action": _phone_signal_next_action(record),
            "due_date": _phone_signal_due_date(record, _phone_signal_next_action(record)),
            "priority": _phone_signal_priority(record, _phone_signal_next_action(record)),
            "stage": _clean_text(str(record.get("stage") or "active")),
            "relationship_type": _clean_text(str(record.get("relationship_type") or "contact")),
            "conversation_label": _clean_text(str(record.get("conversation_label") or "")) or (
                f"SMS thread {record.get('thread_id')}" if _clean_text(str(record.get("thread_id") or "")) else ""
            ),
            "open_loop": summary,
            "notes": _phone_signal_notes(record),
            "source_record_id": _phone_signal_record_id(record),
        },
    }


def relationship_log_interaction(
    person_name: str,
    channel: str = "call",
    summary: str = "",
    company: str = "",
    role: str = "",
    phone: str = "",
    email: str = "",
    place_name: str = "",
    place_ref: str = "",
    conversation_label: str = "",
    conversation_ref: str = "",
    relationship_type: str = "",
    stage: str = "",
    priority: str = "",
    urgency: str = "",
    direction: str = "",
    next_action: str = "",
    next_action_due_at: str = "",
    due_date: str = "",
    follow_up_in_days: int | None = None,
    open_loop: str = "",
    notes: str = "",
    tags_csv: str = "",
    source_app: str = "",
    source_device: str = "",
    source_hardware: str = "",
    source_surface: str = "",
    event_type: str = "",
    phone_metadata: dict[str, Any] | None = None,
    occurred_at: str = "",
    session_id: str = "",
) -> dict:
    """Log a CRM interaction, upsert the person sheet, and update follow-up state."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    normalized_name = _clean_text(person_name)
    if not normalized_name:
        return {"ok": False, "output": "", "error": "person_name is required"}

    normalized_channel = _clean_text(channel) or "call"
    normalized_summary = _clean_text(summary)
    normalized_direction = _clean_text(direction) or "outbound"
    normalized_session_id = _clean_text(session_id) or None
    normalized_due_at = _normalize_due_at(
        next_action_due_at=next_action_due_at,
        follow_up_in_days=follow_up_in_days,
        due_date=due_date,
    )
    source = _build_source(
        source_app=source_app,
        source_device=source_device,
        source_hardware=source_hardware,
        source_surface=source_surface,
    )
    normalized_event_type = _clean_text(event_type) or "relationship.interaction.logged"
    normalized_phone_metadata = _clean_mapping(phone_metadata)
    normalized_occurred_at = _clean_text(occurred_at)
    if normalized_phone_metadata:
        source["phone_metadata"] = normalized_phone_metadata

    enriched_contact = _maybe_enrich_from_contacts(normalized_name)
    normalized_phone = _merge_preferred(enriched_contact.get("phone"), phone)
    normalized_email = _merge_preferred(enriched_contact.get("email"), email)
    normalized_company = _clean_text(company)
    normalized_role = _clean_text(role)
    normalized_place_name = _clean_text(place_name)
    normalized_place_ref = _clean_text(place_ref)
    normalized_conversation_label = _clean_text(conversation_label)
    normalized_conversation_ref = _clean_text(conversation_ref)
    normalized_open_loop = _clean_text(open_loop)
    normalized_next_action = _clean_text(next_action)
    normalized_notes = _clean_text(notes)
    normalized_relationship_type = _clean_text(relationship_type)
    normalized_stage = _clean_text(stage)
    normalized_priority = _clean_text(priority or urgency)
    normalized_tags = _parse_tags(tags_csv)

    existing = _find_person_sheet(
        runtime,
        person_name=normalized_name,
        phone=normalized_phone,
        email=normalized_email,
    )
    existing_metadata = dict(existing.metadata or {}) if existing else {}
    existing_contact = dict(existing_metadata.get("contact") or {})
    existing_relationship = dict(existing_metadata.get("relationship") or {})
    existing_company = _clean_text(existing_contact.get("company"))
    person_ref = f"people/{existing.slug if existing else slugify(normalized_name)}"

    existing_organization_ref = _clean_text(existing_relationship.get("organization_ref"))
    existing_organization_name = _clean_text(existing_relationship.get("organization_name"))
    existing_place_ref = _clean_text(existing_relationship.get("place_ref"))
    existing_place_name = _clean_text(existing_relationship.get("place_name"))
    existing_conversation_ref = _clean_text(existing_relationship.get("conversation_ref"))
    existing_conversation_label = _clean_text(existing_relationship.get("conversation_label"))

    organization_title = normalized_company or existing_organization_name or existing_company
    organization_ref_input = (
        existing_organization_ref
        if not normalized_company
        or _clean_lower(existing_organization_name) == _clean_lower(normalized_company)
        or _clean_lower(existing_company) == _clean_lower(normalized_company)
        else ""
    )
    place_has_incoming = bool(normalized_place_name or normalized_place_ref)
    place_title = normalized_place_name or existing_place_name
    place_ref_input = normalized_place_ref if normalized_place_ref else (existing_place_ref if not place_has_incoming else "")
    conversation_has_incoming = bool(normalized_conversation_label or normalized_conversation_ref)
    conversation_title = normalized_conversation_label or existing_conversation_label
    conversation_ref_input = (
        normalized_conversation_ref
        if normalized_conversation_ref
        else (existing_conversation_ref if not conversation_has_incoming else "")
    )

    organization_record = None
    if _clean_text(organization_title) or _clean_text(organization_ref_input):
        organization_record = _upsert_linked_context_sheet(
            runtime,
            kind="organization",
            title=organization_title or organization_ref_input,
            ref=organization_ref_input,
            person_name=normalized_name,
            person_ref=person_ref,
            channel=normalized_channel,
            direction=normalized_direction,
            summary=normalized_summary,
            metadata={
                "company": organization_title or normalized_company,
                "person_name": normalized_name,
                "person_ref": person_ref,
                "role": normalized_role or _clean_text(existing_contact.get("role")),
                "email": normalized_email,
                "phone": normalized_phone,
            },
            extra_lines=[
                _format_linked_context_line("Role", normalized_role or _clean_text(existing_contact.get("role"))),
                _format_linked_context_line("Email", normalized_email),
                _format_linked_context_line("Phone", normalized_phone),
            ],
        )

    place_record = None
    if _clean_text(place_title) or _clean_text(place_ref_input):
        place_record = _upsert_linked_context_sheet(
            runtime,
            kind="place",
            title=place_title or place_ref_input,
            ref=place_ref_input,
            person_name=normalized_name,
            person_ref=person_ref,
            channel=normalized_channel,
            direction=normalized_direction,
            summary=normalized_summary,
            metadata={
                "person_name": normalized_name,
                "person_ref": person_ref,
            },
            extra_lines=[
                _format_linked_context_line("Place", place_title or place_ref_input),
            ],
        )

    conversation_record = None
    if _clean_text(conversation_title) or _clean_text(conversation_ref_input):
        conversation_record = _upsert_linked_context_sheet(
            runtime,
            kind="conversation",
            title=conversation_title or conversation_ref_input,
            ref=conversation_ref_input,
            person_name=normalized_name,
            person_ref=person_ref,
            channel=normalized_channel,
            direction=normalized_direction,
            summary=normalized_summary,
            metadata={
                "person_name": normalized_name,
                "person_ref": person_ref,
            },
            extra_lines=[
                _format_linked_context_line("Conversation", conversation_title or conversation_ref_input),
            ],
        )

    merged_contact = {
        "company": _merge_preferred(existing_contact.get("company"), normalized_company),
        "role": _merge_preferred(existing_contact.get("role"), normalized_role),
        "phone": _merge_preferred(existing_contact.get("phone"), normalized_phone),
        "email": _merge_preferred(existing_contact.get("email"), normalized_email),
    }
    merged_contact = {key: value for key, value in merged_contact.items() if value}

    merged_relationship = dict(existing_relationship)
    merged_relationship["preferred_channel"] = _merge_preferred(
        existing_relationship.get("preferred_channel"),
        normalized_channel,
        fallback="call",
    )
    merged_relationship["relationship_type"] = _merge_preferred(
        existing_relationship.get("relationship_type"),
        normalized_relationship_type,
        fallback="contact",
    )
    merged_relationship["stage"] = _merge_preferred(
        existing_relationship.get("stage"),
        normalized_stage,
        fallback="active",
    )
    merged_relationship["priority"] = _merge_preferred(
        existing_relationship.get("priority"),
        normalized_priority,
        fallback="medium",
    )
    merged_relationship["owner"] = _merge_preferred(
        existing_relationship.get("owner"),
        None,
        fallback="Tyler",
    )
    merged_relationship["last_touch_at"] = utc_now()
    merged_relationship["last_interaction_channel"] = normalized_channel
    merged_relationship["last_interaction_direction"] = normalized_direction
    if normalized_occurred_at:
        merged_relationship["last_phone_event_at"] = normalized_occurred_at
    if normalized_phone_metadata:
        merged_relationship["last_phone_metadata"] = normalized_phone_metadata
    merged_relationship["thread_summary"] = _merge_preferred(
        existing_relationship.get("thread_summary"),
        normalized_summary,
        fallback=_clean_text(existing.body).splitlines()[0] if existing and existing.body else "",
    )
    merged_relationship["open_loop"] = _merge_preferred(
        existing_relationship.get("open_loop"),
        normalized_open_loop,
    )
    merged_relationship["notes"] = _merge_preferred(
        existing_relationship.get("notes"),
        normalized_notes,
    )
    if organization_record:
        merged_relationship["organization_ref"] = organization_record["ref"]
        merged_relationship["organization_name"] = organization_record["name"]
    elif existing_organization_ref or existing_organization_name:
        merged_relationship["organization_ref"] = existing_organization_ref
        merged_relationship["organization_name"] = existing_organization_name or organization_title
    if place_record:
        merged_relationship["place_ref"] = place_record["ref"]
        merged_relationship["place_name"] = place_record["name"]
    elif existing_place_ref or existing_place_name:
        merged_relationship["place_ref"] = existing_place_ref
        merged_relationship["place_name"] = existing_place_name or place_title
    if conversation_record:
        merged_relationship["conversation_ref"] = conversation_record["ref"]
        merged_relationship["conversation_label"] = conversation_record["name"]
    elif existing_conversation_ref or existing_conversation_label:
        merged_relationship["conversation_ref"] = existing_conversation_ref
        merged_relationship["conversation_label"] = existing_conversation_label or conversation_title
    merged_relationship["interaction_count"] = int(existing_relationship.get("interaction_count", 0) or 0) + 1

    if normalized_next_action:
        merged_relationship["next_action"] = normalized_next_action
    elif not existing_relationship.get("next_action"):
        merged_relationship["next_action"] = ""

    if normalized_due_at:
        merged_relationship["next_action_due_at"] = normalized_due_at
    elif normalized_next_action and not existing_relationship.get("next_action_due_at"):
        merged_relationship["next_action_due_at"] = None

    if merged_relationship.get("next_action_due_at") is None:
        merged_relationship.pop("next_action_due_at", None)

    merged_tags = _dedupe_strings(list(existing_metadata.get("tags") or []) + normalized_tags)
    metadata = {
        **existing_metadata,
        "contact": merged_contact,
        "relationship": merged_relationship,
        "tags": merged_tags,
        "auto_body": bool(existing_metadata.get("auto_body", True)),
    }

    should_generate_body = not existing or not _clean_text(existing.body) or bool(existing_metadata.get("auto_body", True))
    body = existing.body if existing and _clean_text(existing.body) and not should_generate_body else _generate_person_body(
        name=normalized_name,
        company=merged_contact.get("company", ""),
        role=merged_contact.get("role", ""),
        relationship_type=str(merged_relationship.get("relationship_type", "")),
        priority=str(merged_relationship.get("priority", "")),
        stage=str(merged_relationship.get("stage", "")),
        channel=str(merged_relationship.get("preferred_channel", "")),
        summary=normalized_summary or str(merged_relationship.get("thread_summary", "")),
        next_action=str(merged_relationship.get("next_action", "")),
        next_action_due_at=merged_relationship.get("next_action_due_at"),
        open_loop=str(merged_relationship.get("open_loop", "")),
        notes=str(merged_relationship.get("notes", "")),
        phone=merged_contact.get("phone", ""),
        email=merged_contact.get("email", ""),
        tags=merged_tags,
        organization_ref=str(merged_relationship.get("organization_ref", "")),
        organization_name=str(merged_relationship.get("organization_name", "")),
        place_ref=str(merged_relationship.get("place_ref", "")),
        place_name=str(merged_relationship.get("place_name", "")),
        conversation_ref=str(merged_relationship.get("conversation_ref", "")),
        conversation_label=str(merged_relationship.get("conversation_label", "")),
    )

    linked_refs = _dedupe_strings([
        str(merged_relationship.get("organization_ref", "")),
        str(merged_relationship.get("place_ref", "")),
        str(merged_relationship.get("conversation_ref", "")),
        *[ref for ref in list(existing.links if existing else []) if _clean_text(ref) != person_ref],
    ])

    sheet = runtime.create_context_sheet(
        kind="person",
        name=normalized_name,
        slug=existing.slug if existing else slugify(normalized_name),
        body=body,
        links=linked_refs,
        source_refs=list(existing.source_refs if existing else []),
        metadata=metadata,
        status=existing.status if existing else "active",
        confidence=max(existing.confidence if existing else 0.0, 0.95 if normalized_summary else 0.85),
    )
    person_ref = f"people/{sheet.slug}"
    linked_entity_refs = [person_ref]
    for candidate_ref in (
        _clean_text(str(merged_relationship.get("organization_ref", ""))),
        _clean_text(str(merged_relationship.get("place_ref", ""))),
        _clean_text(str(merged_relationship.get("conversation_ref", ""))),
    ):
        if candidate_ref:
            linked_entity_refs.append(candidate_ref)
    linked_entity_refs = _dedupe_strings(linked_entity_refs)
    event_payload = {
        "person_ref": person_ref,
        "person_name": sheet.name,
        "channel": normalized_channel,
        "direction": normalized_direction,
        "summary": normalized_summary,
        "company": merged_contact.get("company", ""),
        "role": merged_contact.get("role", ""),
        "phone": merged_contact.get("phone", ""),
        "email": merged_contact.get("email", ""),
        "next_action": str(merged_relationship.get("next_action", "")),
        "next_action_due_at": merged_relationship.get("next_action_due_at"),
        "open_loop": str(merged_relationship.get("open_loop", "")),
        "priority": str(merged_relationship.get("priority", "")),
        "stage": str(merged_relationship.get("stage", "")),
        "relationship_type": str(merged_relationship.get("relationship_type", "")),
        "tags": merged_tags,
        "contact_enriched": bool(enriched_contact),
        "organization_ref": str(merged_relationship.get("organization_ref", "")),
        "organization_name": str(merged_relationship.get("organization_name", "")),
        "place_ref": str(merged_relationship.get("place_ref", "")),
        "place_name": str(merged_relationship.get("place_name", "")),
        "conversation_ref": str(merged_relationship.get("conversation_ref", "")),
        "conversation_label": str(merged_relationship.get("conversation_label", "")),
        "phone_metadata": normalized_phone_metadata,
        "occurred_at": normalized_occurred_at,
    }
    event = runtime.append_context_event(
        event_type=normalized_event_type,
        summary=f"Logged {normalized_channel} interaction with {sheet.name}",
        payload=event_payload,
        source=source,
        entity_refs=linked_entity_refs,
        session_id=normalized_session_id,
    )

    followup = _relationship_record_from_sheet(sheet, pinned_refs=_load_pins(runtime))
    return {
        "ok": True,
        "output": {
            "person_sheet": sheet.to_dict(),
            "interaction_event": event.to_dict(),
            "followup": followup,
        },
        "error": None,
    }


def relationship_ingest_phone_metadata(
    person_name: str,
    channel: str = "call",
    direction: str = "",
    phone_number: str = "",
    summary: str = "",
    company: str = "",
    role: str = "",
    place_name: str = "",
    place_ref: str = "",
    conversation_label: str = "",
    conversation_ref: str = "",
    relationship_type: str = "",
    stage: str = "",
    priority: str = "",
    next_action: str = "",
    next_action_due_at: str = "",
    due_date: str = "",
    follow_up_in_days: int | None = None,
    duration_seconds: int | None = None,
    occurred_at: str = "",
    thread_id: str = "",
    message_id: str = "",
    external_event_id: str = "",
    call_status: str = "",
    voicemail: bool = False,
    transcript: str = "",
    transcript_summary: str = "",
    snippet: str = "",
    source_app: str = "Phone",
    source_device: str = "",
    source_hardware: str = "",
    source_surface: str = "phone.metadata",
    session_id: str = "",
) -> dict:
    """Ingest structured phone metadata into the relationship graph."""
    normalized_person_name = _clean_text(person_name)
    normalized_channel = _clean_text(channel) or "call"
    normalized_direction = _clean_text(direction)
    normalized_phone_number = _clean_text(phone_number)
    if not normalized_person_name:
        normalized_person_name = normalized_phone_number or "Unknown phone contact"
    normalized_summary = _clean_text(summary) or _clean_text(transcript_summary) or _clean_text(snippet)
    if not normalized_summary:
        verb = "Incoming" if _clean_lower(normalized_direction) in {"inbound", "incoming"} else "Outgoing"
        normalized_summary = f"{verb} {normalized_channel} with {normalized_person_name}"
        if normalized_phone_number:
            normalized_summary += f" ({normalized_phone_number})"

    source_record_id = _clean_text(external_event_id)
    if not source_record_id:
        source_record_id = "|".join(
            part
            for part in [
                normalized_channel,
                normalized_phone_number,
                _clean_text(occurred_at),
                _clean_text(thread_id),
                _clean_text(message_id),
                _clean_text(call_status),
                normalized_summary[:80],
            ]
            if part
        )

    runtime = _get_runtime()
    if source_record_id and source_record_id in _existing_phone_signal_ids(runtime):
        return {
            "ok": True,
            "output": {
                "skipped": True,
                "reason": "duplicate_phone_metadata",
                "source_record_id": source_record_id,
                "person_name": normalized_person_name,
            },
            "error": None,
        }

    phone_metadata = _clean_mapping(
        {
            "channel": normalized_channel,
            "direction": normalized_direction,
            "phone_number": normalized_phone_number,
            "duration_seconds": duration_seconds,
            "occurred_at": _clean_text(occurred_at),
            "thread_id": _clean_text(thread_id),
            "message_id": _clean_text(message_id),
            "external_event_id": _clean_text(external_event_id),
            "source_record_id": source_record_id,
            "call_status": _clean_text(call_status),
            "voicemail": voicemail,
            "transcript": _clean_text(transcript),
            "transcript_summary": _clean_text(transcript_summary),
            "snippet": _clean_text(snippet),
        }
    )

    return relationship_log_interaction(
        person_name=normalized_person_name,
        channel=normalized_channel,
        summary=normalized_summary,
        company=company,
        role=role,
        phone=normalized_phone_number,
        place_name=place_name,
        place_ref=place_ref,
        conversation_label=conversation_label,
        conversation_ref=conversation_ref,
        relationship_type=relationship_type,
        stage=stage,
        priority=priority,
        next_action=next_action,
        next_action_due_at=next_action_due_at,
        due_date=due_date,
        follow_up_in_days=follow_up_in_days,
        direction=normalized_direction,
        source_app=source_app,
        source_device=source_device,
        source_hardware=source_hardware,
        source_surface=source_surface,
        event_type="relationship.phone_signal.ingested",
        phone_metadata=phone_metadata,
        occurred_at=occurred_at,
        session_id=session_id,
    )


def relationship_list_followups(limit: int = 8) -> dict:
    """List the current CRM follow-up queue derived from canonical person sheets."""
    runtime = _get_runtime()
    runtime.init_context_repo()
    people = runtime.context_repository.list_sheets(kind="person", limit=500)
    pinned_refs = _load_pins(runtime)

    items = []
    for sheet in people:
        metadata = dict(sheet.metadata or {})
        relationship = dict(metadata.get("relationship") or {})
        if not relationship:
            continue
        item = _relationship_record_from_sheet(sheet, pinned_refs=pinned_refs)
        if not item.get("next_action") and not item.get("open_loop") and not item.get("thread_summary"):
            continue
        items.append(item)

    items.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            item.get("next_action_due_at") or "9999-12-31T00:00:00+00:00",
            str(item.get("full_name", "")).lower(),
        )
    )
    return {
        "ok": True,
        "output": items[:limit],
        "error": None,
    }


def relationship_get_briefing(limit: int = 5) -> dict:
    """Generate a concise relationship briefing from the live follow-up queue."""
    queue = relationship_list_followups(limit=limit)
    items = list(queue.get("output") or [])
    overdue = sum(1 for item in items if item.get("overdue"))
    high_priority = sum(1 for item in items if _clean_lower(item.get("priority")) == "high")

    headline_parts = [
        f"{len(items)} priority follow-up{'s' if len(items) != 1 else ''}",
        f"{overdue} overdue",
    ]

    if items:
        top_names = ", ".join(item["full_name"] for item in items[:3])
        briefing_text = f"Start with {top_names}. Clear overdue threads before lower-priority relationship work."
    else:
        briefing_text = "No relationship follow-ups are queued yet. Log a call, text, or meeting to start building the CRM memory."

    return {
        "ok": True,
        "output": {
            "headline": ", ".join(headline_parts),
            "briefing_text": briefing_text,
            "stats": {
                "priority_followups": len(items),
                "high_priority": high_priority,
                "overdue_followups": overdue,
            },
            "priority_followups": items,
            "generated_at": utc_now(),
            "source": "context_repo",
        },
        "error": None,
    }


def relationship_import_contacts(limit: int = 200, query: str = "", session_id: str = "") -> dict:
    """Backfill canonical person sheets from the trusted desktop contacts source."""
    runtime = _get_runtime()
    runtime.init_context_repo()

    contact_result = contacts_list(limit=limit, query=query)
    if not contact_result.get("ok"):
        return {
            "ok": False,
            "output": "",
            "error": contact_result.get("error") or "Failed to list contacts",
        }

    created = 0
    updated = 0
    skipped = 0
    imported_refs: list[str] = []
    preview: list[dict[str, Any]] = []

    for raw_contact in list(contact_result.get("output") or []):
        if not isinstance(raw_contact, dict):
            continue

        person_name = _clean_text(raw_contact.get("full_name"))
        if not person_name:
            skipped += 1
            continue

        company = _clean_text(raw_contact.get("company"))
        role = _clean_text(raw_contact.get("role"))
        phone = _clean_text(raw_contact.get("phone"))
        email = _clean_text(raw_contact.get("email"))

        existing = _find_person_sheet(runtime, person_name=person_name, phone=phone, email=email)
        existing_metadata = dict(existing.metadata or {}) if existing else {}
        existing_contact = dict(existing_metadata.get("contact") or {})
        existing_relationship = dict(existing_metadata.get("relationship") or {})
        person_ref = f"people/{existing.slug if existing else slugify(person_name)}"

        existing_organization_ref = _clean_text(existing_relationship.get("organization_ref"))
        existing_organization_name = _clean_text(existing_relationship.get("organization_name"))
        organization_title = company or existing_organization_name or _clean_text(existing_contact.get("company"))
        organization_ref_input = (
            existing_organization_ref
            if not company
            or _clean_lower(existing_organization_name) == _clean_lower(company)
            or _clean_lower(_clean_text(existing_contact.get("company"))) == _clean_lower(company)
            else ""
        )

        merged_contact = {
            "company": _merge_preferred(existing_contact.get("company"), company),
            "role": _merge_preferred(existing_contact.get("role"), role),
            "phone": _merge_preferred(existing_contact.get("phone"), phone),
            "email": _merge_preferred(existing_contact.get("email"), email),
        }
        merged_contact = {key: value for key, value in merged_contact.items() if value}

        organization_record = None
        if _clean_text(organization_title) or _clean_text(organization_ref_input):
            organization_record = _upsert_linked_context_sheet(
                runtime,
                kind="organization",
                title=organization_title or organization_ref_input,
                ref=organization_ref_input,
                person_name=person_name,
                person_ref=person_ref,
                channel="email" if merged_contact.get("email") else "call" if merged_contact.get("phone") else "unknown",
                direction="imported",
                summary="Imported from Contacts.app",
                metadata={
                    "company": organization_title or company,
                    "person_name": person_name,
                    "person_ref": person_ref,
                    "role": merged_contact.get("role", ""),
                    "email": merged_contact.get("email", ""),
                    "phone": merged_contact.get("phone", ""),
                    "imported_from_contacts": True,
                },
                extra_lines=[
                    _format_linked_context_line("Role", merged_contact.get("role", "")),
                    _format_linked_context_line("Email", merged_contact.get("email", "")),
                    _format_linked_context_line("Phone", merged_contact.get("phone", "")),
                ],
            )

        merged_relationship = dict(existing_relationship)
        merged_relationship["preferred_channel"] = _merge_preferred(
            existing_relationship.get("preferred_channel"),
            "call" if phone else "email" if email else "unknown",
            fallback="unknown",
        )
        merged_relationship["relationship_type"] = _merge_preferred(
            existing_relationship.get("relationship_type"),
            "contact",
            fallback="contact",
        )
        merged_relationship["stage"] = _merge_preferred(
            existing_relationship.get("stage"),
            "new",
            fallback="new",
        )
        merged_relationship["priority"] = _merge_preferred(
            existing_relationship.get("priority"),
            "medium",
            fallback="medium",
        )
        merged_relationship["owner"] = _merge_preferred(
            existing_relationship.get("owner"),
            None,
            fallback="Tyler",
        )
        if organization_record:
            merged_relationship["organization_ref"] = organization_record["ref"]
            merged_relationship["organization_name"] = organization_record["name"]
        elif existing_organization_ref or existing_organization_name:
            merged_relationship["organization_ref"] = existing_organization_ref
            merged_relationship["organization_name"] = existing_organization_name or organization_title

        metadata = {
            **existing_metadata,
            "contact": merged_contact,
            "relationship": merged_relationship,
            "tags": _dedupe_strings(list(existing_metadata.get("tags") or [])),
            "auto_body": bool(existing_metadata.get("auto_body", True)),
            "imported_from_contacts": True,
        }

        should_generate_body = (
            not existing
            or not _clean_text(existing.body)
            or bool(existing_metadata.get("auto_body", True))
        )
        body = existing.body if existing and _clean_text(existing.body) and not should_generate_body else _generate_person_body(
            name=person_name,
            company=merged_contact.get("company", ""),
            role=merged_contact.get("role", ""),
            relationship_type=str(merged_relationship.get("relationship_type", "")),
            priority=str(merged_relationship.get("priority", "")),
            stage=str(merged_relationship.get("stage", "")),
            channel=str(merged_relationship.get("preferred_channel", "")),
            summary=str(merged_relationship.get("thread_summary", "")),
            next_action=str(merged_relationship.get("next_action", "")),
            next_action_due_at=merged_relationship.get("next_action_due_at"),
            open_loop=str(merged_relationship.get("open_loop", "")),
            notes=str(merged_relationship.get("notes", "")),
            phone=merged_contact.get("phone", ""),
            email=merged_contact.get("email", ""),
            tags=list(metadata.get("tags") or []),
            organization_ref=str(merged_relationship.get("organization_ref", "")),
            organization_name=str(merged_relationship.get("organization_name", "")),
        )

        linked_refs = _dedupe_strings([
            str(merged_relationship.get("organization_ref", "")),
            *[ref for ref in list(existing.links if existing else []) if _clean_text(ref) != person_ref],
        ])

        sheet = runtime.create_context_sheet(
            kind="person",
            name=person_name,
            slug=existing.slug if existing else slugify(person_name),
            body=body,
            links=linked_refs,
            source_refs=list(existing.source_refs if existing else []),
            metadata=metadata,
            status=existing.status if existing else "active",
            confidence=max(existing.confidence if existing else 0.0, 0.85),
        )

        imported_refs.append(f"people/{sheet.slug}")
        if existing:
            updated += 1
        else:
            created += 1

        if len(preview) < 10:
            preview.append({
                "person_ref": f"people/{sheet.slug}",
                "full_name": sheet.name,
                "company": merged_contact.get("company", ""),
                "role": merged_contact.get("role", ""),
                "phone": merged_contact.get("phone", ""),
                "email": merged_contact.get("email", ""),
                "path": sheet.path,
            })

    event = runtime.append_context_event(
        event_type="relationship.contacts.imported",
        summary=f"Imported {created + updated} contacts from desktop Contacts.app",
        payload={
            "query": _clean_text(query),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "imported_count": created + updated,
        },
        source={"app": "Contacts.app", "device": "desktop", "surface": "relationship_import_contacts"},
        entity_refs=imported_refs[:50],
        session_id=_clean_text(session_id) or None,
    )

    return {
        "ok": True,
        "output": {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "imported_count": created + updated,
            "preview": preview,
            "event": event.to_dict(),
        },
        "error": None,
    }


TOOLS = {
    "relationship_log_interaction": {
        "fn": relationship_log_interaction,
        "description": "Log a call, text, meeting, or other relationship interaction and update the CRM follow-up state.",
        "params": {
            "person_name": "str",
            "channel": "str='call'",
            "summary": "str=''",
            "company": "str=''",
            "role": "str=''",
            "phone": "str=''",
            "email": "str=''",
            "place_name": "str=''",
            "place_ref": "str=''",
            "conversation_label": "str=''",
            "conversation_ref": "str=''",
            "relationship_type": "str=''",
            "stage": "str=''",
            "priority": "str=''",
            "urgency": "str=''",
            "direction": "str=''",
            "next_action": "str=''",
            "next_action_due_at": "str=''",
            "due_date": "str=''",
            "follow_up_in_days": "int=",
            "open_loop": "str=''",
            "notes": "str=''",
            "tags_csv": "str=''",
            "source_app": "str=''",
            "source_device": "str=''",
            "source_hardware": "str=''",
            "source_surface": "str=''",
            "event_type": "str=''",
            "phone_metadata": "dict=",
            "occurred_at": "str=''",
            "session_id": "str=''",
        },
    },
    "relationship_ingest_phone_metadata": {
        "fn": relationship_ingest_phone_metadata,
        "description": "Ingest structured phone call or message metadata into the relationship graph and follow-up state.",
        "params": {
            "person_name": "str",
            "channel": "str='call'",
            "direction": "str=''",
            "phone_number": "str=''",
            "summary": "str=''",
            "company": "str=''",
            "role": "str=''",
            "place_name": "str=''",
            "place_ref": "str=''",
            "conversation_label": "str=''",
            "conversation_ref": "str=''",
            "relationship_type": "str=''",
            "stage": "str=''",
            "priority": "str=''",
            "next_action": "str=''",
            "next_action_due_at": "str=''",
            "due_date": "str=''",
            "follow_up_in_days": "int=",
            "duration_seconds": "int=",
            "occurred_at": "str=''",
            "thread_id": "str=''",
            "message_id": "str=''",
            "external_event_id": "str=''",
            "call_status": "str=''",
            "voicemail": "bool=False",
            "transcript": "str=''",
            "transcript_summary": "str=''",
            "snippet": "str=''",
            "source_app": "str='Phone'",
            "source_device": "str=''",
            "source_hardware": "str=''",
            "source_surface": "str='phone.metadata'",
            "session_id": "str=''",
        },
    },
    "relationship_list_followups": {
        "fn": relationship_list_followups,
        "description": "List the current relationship follow-up queue derived from canonical person sheets.",
        "params": {
            "limit": "int=8",
        },
    },
    "relationship_get_briefing": {
        "fn": relationship_get_briefing,
        "description": "Generate a relationship briefing with the highest-priority follow-ups.",
        "params": {
            "limit": "int=5",
        },
    },
    "relationship_import_contacts": {
        "fn": relationship_import_contacts,
        "description": "Import contacts from the trusted desktop source into canonical person sheets for CRM bootstrap.",
        "params": {
            "limit": "int=200",
            "query": "str=''",
            "session_id": "str=''",
        },
    },
}
