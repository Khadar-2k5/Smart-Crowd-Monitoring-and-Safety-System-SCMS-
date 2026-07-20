"""Small reusable helpers for input validation and response formatting."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import jsonify
from werkzeug.utils import secure_filename

from backend.config import Config


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_identifier(value: str | None, prefix: str = "item") -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_-]", "", value or "")[:64]
    return candidate or f"{prefix}_{uuid.uuid4().hex[:12]}"


def unique_filename(filename: str) -> str:
    clean_name = secure_filename(filename)
    if not clean_name or "." not in clean_name:
        raise ValueError("A video filename with an extension is required.")
    extension = clean_name.rsplit(".", 1)[1].lower()
    if extension not in Config.ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video format. Allowed formats: {', '.join(sorted(Config.ALLOWED_VIDEO_EXTENSIONS))}.")
    return f"{Path(clean_name).stem}_{uuid.uuid4().hex[:10]}.{extension}"


def success(data: Any = None, message: str | None = None, status: int = 200):
    payload: dict[str, Any] = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def failure(message: str, status: int = 400, details: Any = None):
    payload: dict[str, Any] = {"success": False, "message": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status
