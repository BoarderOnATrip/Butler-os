#!/usr/bin/env python3
"""
aiButler CRM prototype adapter.

This is the phone-first CRM prototype layer for aiButler:
  - loads a local relationship snapshot
  - produces an executive briefing
  - ranks next-best follow-ups

The local snapshot is intentional for the prototype phase. It keeps Butler
usable before the Mira API adapter is fully wired. The shape is designed so a
future `MiraCRMAdapter` can replace the snapshot loader without changing the
phone or bridge contracts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from runtime.models import utc_now

DEFAULT_CRM_DIR = Path.home() / ".aibutler" / "crm"
DEFAULT_CRM_SNAPSHOT_PATH = DEFAULT_CRM_DIR / "prototype_snapshot.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_at(days: int = 0, hours: int = 0) -> str:
    return (_utc_now() + timedelta(days=days, hours=hours)).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def resolve_snapshot_path(path: str | Path | None = None) -> Path:
    raw = path or os.environ.get("AIBUTLER_CRM_SNAPSHOT_PATH")
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_CRM_SNAPSHOT_PATH


@dataclass
class RelationshipRecord:
    id: str
    full_name: str
    company: str = ""
    role: str = ""
    stage: str = "new"
    priority: str = "medium"
    channel: str = "sms"
    relationship_type: str = "prospect"
    owner: str = "Tyler"
    last_touch_at: str | None = None
    next_action_due_at: str | None = None
    next_action: str = ""
    open_loop: str = ""
    thread_summary: str = ""
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationshipRecord":
        return cls(
            id=str(data["id"]),
            full_name=str(data["full_name"]),
            company=str(data.get("company", "")),
            role=str(data.get("role", "")),
            stage=str(data.get("stage", "new")),
            priority=str(data.get("priority", "medium")),
            channel=str(data.get("channel", "sms")),
            relationship_type=str(data.get("relationship_type", "prospect")),
            owner=str(data.get("owner", "Tyler")),
            last_touch_at=data.get("last_touch_at"),
            next_action_due_at=data.get("next_action_due_at"),
            next_action=str(data.get("next_action", "")),
            open_loop=str(data.get("open_loop", "")),
            thread_summary=str(data.get("thread_summary", "")),
            notes=str(data.get("notes", "")),
            tags=list(data.get("tags", [])),
        )


def _demo_snapshot() -> dict[str, Any]:
    return {
        "source": "local_snapshot",
        "snapshot_label": "aiButler CRM prototype demo",
        "operator": "Tyler",
        "generated_at": utc_now(),
        "contacts": [
            {
                "id": "rel_sarah_chen",
                "full_name": "Sarah Chen",
                "company": "Northline Ventures",
                "role": "Partner",
                "stage": "warm",
                "priority": "high",
                "channel": "sms",
                "relationship_type": "investor",
                "last_touch_at": _iso_at(days=-9),
                "next_action_due_at": _iso_at(days=-1, hours=-2),
                "next_action": "Send the revised pilot timeline and ask for a 20-minute decision call.",
                "open_loop": "She reviewed the deck and asked whether the desktop runtime is ready for operator trials.",
                "thread_summary": "Positive interest. Waiting on a crisp prototype update and pilot timing.",
                "notes": "Prefers short voice notes and concise proof over long decks.",
                "tags": ["investor", "pilot", "priority"],
            },
            {
                "id": "rel_marco_ruiz",
                "full_name": "Marco Ruiz",
                "company": "Summit OS",
                "role": "Founder",
                "stage": "contacted",
                "priority": "high",
                "channel": "email",
                "relationship_type": "partner",
                "last_touch_at": _iso_at(days=-4),
                "next_action_due_at": _iso_at(hours=6),
                "next_action": "Draft a follow-up with the phone CRM prototype screenshots and offer a workflow walkthrough.",
                "open_loop": "He asked whether Butler can turn inbound threads into a daily action queue.",
                "thread_summary": "Warm partner lead. Needs proof that Butler is more than a voice shell.",
                "notes": "Responds best to practical demos and system diagrams.",
                "tags": ["partner", "workflow"],
            },
            {
                "id": "rel_naomi_brooks",
                "full_name": "Naomi Brooks",
                "company": "Brooks Advisory",
                "role": "Operator",
                "stage": "replied",
                "priority": "medium",
                "channel": "voice",
                "relationship_type": "beta_user",
                "last_touch_at": _iso_at(days=-2),
                "next_action_due_at": _iso_at(days=1),
                "next_action": "Prepare a short beta onboarding checklist and confirm desktop pairing requirements.",
                "open_loop": "She wants help triaging founder follow-ups from her phone between meetings.",
                "thread_summary": "Good beta fit. Wants approvals, voice, and a dependable follow-up list.",
                "notes": "Prefers approval-first flows over auto-send.",
                "tags": ["beta", "ops"],
            },
            {
                "id": "rel_devon_wells",
                "full_name": "Devon Wells",
                "company": "Signal Ridge",
                "role": "Advisor",
                "stage": "warm",
                "priority": "medium",
                "channel": "sms",
                "relationship_type": "advisor",
                "last_touch_at": _iso_at(days=-12),
                "next_action_due_at": _iso_at(days=-3),
                "next_action": "Send a quick status note and ask for feedback on the bridge security model.",
                "open_loop": "He was concerned about exposing full desktop control over the network.",
                "thread_summary": "Helpful advisor. Follow up with the pairing-token and approval model.",
                "notes": "Security angle matters more than branding.",
                "tags": ["advisor", "security"],
            },
            {
                "id": "rel_ella_grant",
                "full_name": "Ella Grant",
                "company": "Grant Capital",
                "role": "Principal",
                "stage": "qualified",
                "priority": "low",
                "channel": "email",
                "relationship_type": "investor",
                "last_touch_at": _iso_at(days=-1),
                "next_action_due_at": _iso_at(days=4),
                "next_action": "Send the public GitHub cutover plan once the repo shape is clean.",
                "open_loop": "She asked to see evidence that the open build is coherent and contributor-friendly.",
                "thread_summary": "Healthy thread, not urgent today.",
                "notes": "More interested in execution discipline than hype.",
                "tags": ["investor", "public-build"],
            },
        ],
    }


def seed_demo_snapshot(path: str | Path | None = None, *, force: bool = False) -> dict[str, Any]:
    snapshot_path = resolve_snapshot_path(path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.exists() and not force:
        return json.loads(snapshot_path.read_text())

    payload = _demo_snapshot()
    snapshot_path.write_text(json.dumps(payload, indent=2))
    return payload


def load_snapshot(path: str | Path | None = None) -> tuple[dict[str, Any], list[RelationshipRecord], Path]:
    snapshot_path = resolve_snapshot_path(path)
    if not snapshot_path.exists():
        payload = seed_demo_snapshot(snapshot_path)
    else:
        payload = json.loads(snapshot_path.read_text())

    contacts = [RelationshipRecord.from_dict(row) for row in payload.get("contacts", [])]
    return payload, contacts, snapshot_path


def _priority_base(priority: str) -> int:
    return {
        "critical": 100,
        "high": 80,
        "medium": 55,
        "low": 25,
    }.get(priority.lower(), 40)


def _stage_bonus(stage: str) -> int:
    return {
        "replied": 24,
        "qualified": 18,
        "contacted": 14,
        "warm": 12,
        "new": 8,
    }.get(stage.lower(), 4)


def _timing_bonus(due_at: str | None) -> tuple[int, bool]:
    due = _parse_iso(due_at)
    if not due:
        return 0, False

    now = _utc_now()
    if due <= now:
        overdue_days = max(1, int((now - due).total_seconds() // 86400) + 1)
        return min(45, 20 + overdue_days * 8), True
    if due <= now + timedelta(hours=24):
        return 16, False
    if due <= now + timedelta(days=3):
        return 8, False
    return 0, False


def _touch_staleness_bonus(last_touch_at: str | None) -> int:
    touched = _parse_iso(last_touch_at)
    if not touched:
        return 8
    days_since = (_utc_now() - touched).days
    if days_since >= 14:
        return 12
    if days_since >= 7:
        return 8
    if days_since >= 3:
        return 4
    return 0


def _record_score(record: RelationshipRecord) -> tuple[int, bool]:
    timing_bonus, overdue = _timing_bonus(record.next_action_due_at)
    score = (
        _priority_base(record.priority)
        + _stage_bonus(record.stage)
        + timing_bonus
        + _touch_staleness_bonus(record.last_touch_at)
    )
    return score, overdue


def _format_due_label(value: str | None) -> str:
    parsed = _parse_iso(value)
    if not parsed:
        return "No due date"
    now = _utc_now()
    days = (parsed.date() - now.date()).days
    if parsed < now and days <= 0:
        overdue_days = abs(days) or 1
        return f"Overdue by {overdue_days}d"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"Due in {days}d"


class LocalSnapshotCRMAdapter:
    source_name = "local_snapshot"

    def __init__(self, path: str | Path | None = None):
        self.path = resolve_snapshot_path(path)

    def seed_demo(self, *, force: bool = False) -> dict[str, Any]:
        payload = seed_demo_snapshot(self.path, force=force)
        payload["snapshot_path"] = str(self.path)
        return payload

    def _records(self) -> tuple[dict[str, Any], list[RelationshipRecord]]:
        payload, contacts, _ = load_snapshot(self.path)
        return payload, contacts

    def get_followups(self, limit: int = 8) -> dict[str, Any]:
        payload, contacts = self._records()
        ranked: list[dict[str, Any]] = []
        for record in contacts:
            score, overdue = _record_score(record)
            ranked.append(
                {
                    **record.to_dict(),
                    "score": score,
                    "overdue": overdue,
                    "due_label": _format_due_label(record.next_action_due_at),
                }
            )

        ranked.sort(
            key=lambda item: (
                -int(item["score"]),
                item.get("next_action_due_at") or "9999-12-31T00:00:00+00:00",
                item["full_name"].lower(),
            )
        )

        return {
            "ok": True,
            "source": payload.get("source", self.source_name),
            "snapshot_label": payload.get("snapshot_label", "aiButler CRM snapshot"),
            "generated_at": payload.get("generated_at", utc_now()),
            "snapshot_path": str(self.path),
            "items": ranked[:limit],
            "count": min(limit, len(ranked)),
        }

    def get_briefing(
        self,
        *,
        pending_approvals: int = 0,
        pending_tasks: int = 0,
        limit: int = 5,
    ) -> dict[str, Any]:
        followups = self.get_followups(limit=limit)
        items = followups["items"]
        overdue = sum(1 for item in items if item["overdue"])
        high_priority = sum(1 for item in items if str(item["priority"]).lower() == "high")

        headline_parts = [
            f"{len(items)} priority follow-up{'s' if len(items) != 1 else ''}",
            f"{overdue} overdue",
        ]
        if pending_approvals:
            headline_parts.append(f"{pending_approvals} approval{'s' if pending_approvals != 1 else ''} waiting")

        briefing_text = (
            "Start with overdue follow-ups first. "
            "Then clear any waiting approvals before handing work to the desktop runtime."
        )

        return {
            "ok": True,
            "source": followups["source"],
            "snapshot_label": followups["snapshot_label"],
            "generated_at": followups["generated_at"],
            "snapshot_path": followups["snapshot_path"],
            "headline": ", ".join(headline_parts),
            "briefing_text": briefing_text,
            "stats": {
                "priority_followups": len(items),
                "high_priority": high_priority,
                "overdue_followups": overdue,
                "pending_approvals": pending_approvals,
                "pending_tasks": pending_tasks,
            },
            "priority_followups": items,
        }


def get_crm_adapter(path: str | Path | None = None) -> LocalSnapshotCRMAdapter:
    return LocalSnapshotCRMAdapter(path)
