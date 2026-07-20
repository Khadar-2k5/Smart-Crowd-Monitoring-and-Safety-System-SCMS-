"""Central configuration for the Smart Crowd Monitoring application."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    path = Path(value) if value else default
    return path if path.is_absolute() else PROJECT_ROOT / path


class Config:
    """Runtime configuration with environment-variable overrides."""

    SECRET_KEY = os.getenv("SCM_SECRET_KEY", "change-this-secret-in-production")
    MAX_CONTENT_LENGTH = int(os.getenv("SCM_MAX_UPLOAD_BYTES", 1024 * 1024 * 1024))
    HOST = os.getenv("SCM_HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", os.getenv("SCM_PORT", "5000")))
    ENVIRONMENT = os.getenv("SCM_ENVIRONMENT", os.getenv("FLASK_ENV", "production")).lower()
    DEBUG = ENVIRONMENT not in {"production", "prod"} and os.getenv("SCM_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
    JSON_SORT_KEYS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SCM_SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SCM_SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
    PROJECT_ROOT = PROJECT_ROOT
    STORAGE_ROOT = _path_from_env("SCM_STORAGE_ROOT", PROJECT_ROOT)
    UPLOAD_DIR = _path_from_env("SCM_UPLOAD_DIR", STORAGE_ROOT / "uploads")
    SCREENSHOT_DIR = _path_from_env("SCM_SCREENSHOT_DIR", STORAGE_ROOT / "screenshots")
    EXPORT_DIR = _path_from_env("SCM_EXPORT_DIR", STORAGE_ROOT / "exports")
    LOG_DIR = _path_from_env("SCM_LOG_DIR", STORAGE_ROOT / "logs")
    MODEL_DIR = _path_from_env("SCM_MODEL_DIR", PROJECT_ROOT / "models")
    DATA_DIR = _path_from_env("SCM_DATA_DIR", STORAGE_ROOT / "data")
    DATABASE_PATH = DATA_DIR / "smart_crowd.db"
    MODEL_PATH = _path_from_env("SCM_MODEL_PATH", MODEL_DIR / "yolov8n.pt")
    DEFAULT_CONFIDENCE = float(os.getenv("SCM_CONFIDENCE", "0.45"))
    DEFAULT_CROWD_THRESHOLD = int(os.getenv("SCM_CROWD_THRESHOLD", "20"))
    DEFAULT_ALERT_COOLDOWN_SECONDS = int(os.getenv("SCM_ALERT_COOLDOWN", "20"))
    DEFAULT_TARGET_INFERENCE_FPS = int(os.getenv("SCM_TARGET_INFERENCE_FPS", "12"))
    MAX_CAMERAS = int(os.getenv("SCM_MAX_CAMERAS", "8"))
    ANALYTICS_SAMPLE_SECONDS = int(os.getenv("SCM_ANALYTICS_SAMPLE_SECONDS", "5"))
    ANALYTICS_RETENTION_DAYS = int(os.getenv("SCM_ANALYTICS_RETENTION_DAYS", "7"))
    CAMERA_FRAME_WIDTH = int(os.getenv("SCM_CAMERA_FRAME_WIDTH", "1280"))
    CAMERA_FRAME_HEIGHT = int(os.getenv("SCM_CAMERA_FRAME_HEIGHT", "720"))
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "m4v", "webm"}

    @classmethod
    def create_directories(cls) -> None:
        for directory in (
            cls.UPLOAD_DIR,
            cls.SCREENSHOT_DIR,
            cls.EXPORT_DIR,
            cls.LOG_DIR,
            cls.MODEL_DIR,
            cls.DATA_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)
