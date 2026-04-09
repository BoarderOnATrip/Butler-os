#!/usr/bin/env python3
"""
aiButler runtime models.

These objects are the first typed spine for Butler's approval-first runtime:
tool specs, sessions, tasks, approvals, memory, capability grants, and receipts.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalPolicy:
    """Human approval posture for a capability or tool."""

    required: bool = False
    reason: str = ""
    live_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityGrant:
    """Represents permission to use a named Butler capability."""

    capability: str
    granted: bool = False
    scope: str = "none"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ButlerSession:
    """Conversation and execution container for one Butler interaction thread."""

    id: str
    user_id: str
    surface: str
    status: str = "active"
    permission_mode: str = "standard"
    full_access_expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    capability_grants: list[CapabilityGrant] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capability_grants"] = [grant.to_dict() for grant in self.capability_grants]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ButlerSession":
        grants = [CapabilityGrant(**grant) for grant in data.get("capability_grants", [])]
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            surface=data["surface"],
            status=data.get("status", "active"),
            permission_mode=data.get("permission_mode", "standard"),
            full_access_expires_at=data.get("full_access_expires_at"),
            metadata=data.get("metadata", {}),
            capability_grants=grants,
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


@dataclass
class ButlerTask:
    """Tracked unit of work inside a Butler session."""

    id: str
    session_id: str
    title: str
    kind: str = "general"
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ButlerTask":
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            title=data["title"],
            kind=data.get("kind", "general"),
            status=data.get("status", "pending"),
            payload=data.get("payload", {}),
            result=data.get("result"),
            error=data.get("error"),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


@dataclass
class ApprovalRequest:
    """Human approval request for a privileged action."""

    id: str
    session_id: str
    tool_name: str
    reason: str
    args: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    actor: str | None = None
    note: str = ""
    requested_at: str = field(default_factory=utc_now)
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            tool_name=data["tool_name"],
            reason=data.get("reason", ""),
            args=data.get("args", {}),
            status=data.get("status", "pending"),
            actor=data.get("actor"),
            note=data.get("note", ""),
            requested_at=data.get("requested_at", utc_now()),
            resolved_at=data.get("resolved_at"),
        )


@dataclass
class MemoryRecord:
    """Persisted memory extracted from a Butler session."""

    id: str
    session_id: str
    kind: str
    content: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            kind=data.get("kind", "note"),
            content=data["content"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", utc_now()),
        )


@dataclass
class ContextEvent:
    """Append-only context and provenance event."""

    id: str
    event_type: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    entity_refs: list[str] = field(default_factory=list)
    session_id: str | None = None
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextEvent":
        return cls(
            id=data["id"],
            event_type=data.get("event_type", "context.event"),
            summary=data.get("summary", ""),
            payload=data.get("payload", {}),
            source=data.get("source", {}),
            entity_refs=data.get("entity_refs", []),
            session_id=data.get("session_id"),
            created_at=data.get("created_at", utc_now()),
        )


@dataclass
class ContextPendingItem:
    """Low-confidence or unresolved capture held for later triage."""

    id: str
    capture_kind: str
    title: str
    content: str = ""
    path: str = ""
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    session_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPendingItem":
        return cls(
            id=data["id"],
            capture_kind=data.get("capture_kind", "note"),
            title=data.get("title", ""),
            content=data.get("content", ""),
            path=data.get("path", ""),
            status=data.get("status", "pending"),
            metadata=data.get("metadata", {}),
            source=data.get("source", {}),
            confidence=float(data.get("confidence", 0.0)),
            session_id=data.get("session_id"),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


@dataclass
class ContextSheet:
    """Canonical markdown sheet for a durable context object."""

    id: str
    kind: str
    slug: str
    name: str
    path: str
    body: str = ""
    status: str = "active"
    confidence: float = 1.0
    links: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_confirmed_at: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextSheet":
        return cls(
            id=data["id"],
            kind=data.get("kind", "artifact"),
            slug=data.get("slug", data["id"]),
            name=data.get("name", data["id"]),
            path=data.get("path", ""),
            body=data.get("body", ""),
            status=data.get("status", "active"),
            confidence=float(data.get("confidence", 1.0)),
            links=data.get("links", []),
            source_refs=data.get("source_refs", []),
            metadata=data.get("metadata", {}),
            last_confirmed_at=data.get("last_confirmed_at"),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


@dataclass
class ContinuityPacket:
    """Cross-device handoff packet for phone/desktop continuity."""

    id: str
    kind: str
    title: str
    content: str = ""
    source_device: str = ""
    target_device: str = ""
    source_surface: str = ""
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    lease_owner: str = ""
    lease_expires_at: str | None = None
    consumed_at: str | None = None
    expires_at: str | None = None
    session_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuityPacket":
        return cls(
            id=data["id"],
            kind=data.get("kind", "text"),
            title=data.get("title", ""),
            content=data.get("content", ""),
            source_device=data.get("source_device", ""),
            target_device=data.get("target_device", ""),
            source_surface=data.get("source_surface", ""),
            status=data.get("status", "pending"),
            metadata=data.get("metadata", {}),
            lease_owner=data.get("lease_owner", ""),
            lease_expires_at=data.get("lease_expires_at"),
            consumed_at=data.get("consumed_at"),
            expires_at=data.get("expires_at"),
            session_id=data.get("session_id"),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


@dataclass
class ToolSpec:
    """Typed tool metadata for runtime policy and UI surfaces."""

    name: str
    category: str
    capability: str
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    read_only: bool = False
    risk: str = "low"
    reversible: bool = True
    approval: ApprovalPolicy = field(default_factory=ApprovalPolicy)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["approval"] = self.approval.to_dict()
        return data


@dataclass
class ToolCallReceipt:
    """Minimal action receipt that runtime surfaces can persist or display."""

    session_id: str
    tool_name: str
    args: dict[str, Any]
    ok: bool
    tool_category: str = "general"
    risk: str = "low"
    output: Any = None
    error: str | None = None
    approval_request_id: str | None = None
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
