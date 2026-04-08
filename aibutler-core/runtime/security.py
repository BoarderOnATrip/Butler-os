#!/usr/bin/env python3
"""
aiButler runtime security policy.

Full access is supported, but only as a guarded local operator mode.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

TRUSTED_LOCAL_SURFACES = {"local", "desktop", "cli", "voice"}


def env_enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def full_access_feature_enabled() -> bool:
    """Master feature flag for full-access mode."""
    return env_enabled("AIBUTLER_ENABLE_FULL_ACCESS", default=False)


def full_access_ttl_minutes() -> int:
    """Default full-access lifetime in minutes."""
    raw = os.environ.get("AIBUTLER_FULL_ACCESS_TTL_MINUTES", "30")
    try:
        ttl = int(raw)
    except ValueError:
        ttl = 30
    return max(1, min(ttl, 720))


def arm_token_ttl_minutes() -> int:
    """Default lifetime for a one-time local arming token."""
    raw = os.environ.get("AIBUTLER_ARM_TOKEN_TTL_MINUTES", "5")
    try:
        ttl = int(raw)
    except ValueError:
        ttl = 5
    return max(1, min(ttl, 60))


def trusted_local_session(session) -> bool:
    """Return True only for sessions that are clearly local and not remotely exposed."""
    metadata = session.metadata or {}
    if metadata.get("trusted_local") is True:
        return True
    if metadata.get("remote_origin"):
        return False
    if metadata.get("public_url"):
        return False
    return session.surface in TRUSTED_LOCAL_SURFACES


def future_expiry_iso(minutes: int | None = None) -> str:
    ttl = minutes if minutes is not None else full_access_ttl_minutes()
    return (utc_now_dt() + timedelta(minutes=ttl)).isoformat()


def issue_arm_token() -> str:
    """Generate a short-lived local arming token."""
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    """Hash a token for local-at-rest comparison."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_expired(timestamp: str | None) -> bool:
    if not timestamp:
        return True
    try:
        expires = datetime.fromisoformat(timestamp)
    except ValueError:
        return True
    return utc_now_dt() >= expires
