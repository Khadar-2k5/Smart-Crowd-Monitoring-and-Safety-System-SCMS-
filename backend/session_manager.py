"""Per-browser-session isolation and lifecycle helpers."""

from __future__ import annotations

import re
import shutil
import time
import uuid
from pathlib import Path

from flask import has_request_context, session

from backend.config import Config

SESSION_KEY = "scm_session_id"
SESSION_TTL_SECONDS = int(__import__("os").getenv("SCM_SESSION_TTL_SECONDS", "3600"))
_last_seen: dict[str, float] = {}


def current_session_id() -> str:
    if has_request_context():
        value = session.get(SESSION_KEY)
        if not value or not re.fullmatch(r"[a-f0-9]{32}", str(value)):
            value = uuid.uuid4().hex
            session[SESSION_KEY] = value
        _last_seen[value] = time.monotonic()
        return value
    return "system"


def session_root(session_id: str | None = None) -> Path:
    identifier = session_id or current_session_id()
    root = Config.STORAGE_ROOT / "sessions" / identifier
    for name in ("uploads", "screenshots", "exports", "logs", "data"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def session_path(session_id: str | None, name: str) -> Path:
    return session_root(session_id) / name


def cleanup_expired_sessions(active_ids: set[str] | None = None) -> None:
    now = time.monotonic()
    protected = active_ids or set()
    for identifier, last_seen in list(_last_seen.items()):
        if identifier in protected or now - last_seen <= SESSION_TTL_SECONDS:
            continue
        from backend.camera_manager import discard_manager
        discard_manager(identifier)
        root = Config.STORAGE_ROOT / "sessions" / identifier
        shutil.rmtree(root, ignore_errors=True)
        _last_seen.pop(identifier, None)
