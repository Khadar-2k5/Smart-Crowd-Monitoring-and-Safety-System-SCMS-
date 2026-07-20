"""Settings, system, logs and health REST endpoints."""

from __future__ import annotations

from flask import Blueprint, request

from backend.camera_manager import get_camera_manager
from backend.data_store import get_store
from backend.services.health_service import get_health_service
from backend.utils.helpers import failure, success

api_bp = Blueprint("api", __name__)


def _validate_settings(payload: dict) -> dict:
    allowed = {"confidence_threshold", "crowd_threshold", "alert_cooldown_seconds", "theme", "save_alert_screenshots", "heatmap_opacity", "target_inference_fps"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
    if "confidence_threshold" in payload and not 0.05 <= float(payload["confidence_threshold"]) <= 0.95:
        raise ValueError("confidence_threshold must be between 0.05 and 0.95.")
    if "crowd_threshold" in payload and not 1 <= int(payload["crowd_threshold"]) <= 10000:
        raise ValueError("crowd_threshold must be between 1 and 10000.")
    if "alert_cooldown_seconds" in payload and not 1 <= int(payload["alert_cooldown_seconds"]) <= 3600:
        raise ValueError("alert_cooldown_seconds must be between 1 and 3600.")
    if "theme" in payload and payload["theme"] not in {"dark", "light"}:
        raise ValueError("theme must be dark or light.")
    if "heatmap_opacity" in payload and not 0.05 <= float(payload["heatmap_opacity"]) <= 0.9:
        raise ValueError("heatmap_opacity must be between 0.05 and 0.9.")
    if "target_inference_fps" in payload and not 1 <= int(payload["target_inference_fps"]) <= 60:
        raise ValueError("target_inference_fps must be between 1 and 60.")
    return payload


@api_bp.get("/api")
def api_home():
    return success({"application": "Smart Crowd Monitoring & Safety System", "version": "2.0.0", "documentation": "/api/health"})


@api_bp.get("/api/health")
def health():
    report = get_health_service().check()
    return success(report, status=200 if report["ready"] else 503)


@api_bp.post("/api/system/initialize")
def initialize_system():
    report = get_health_service().initialize()
    return success(report, "System initialization complete." if report["ready"] else "System diagnostics found critical issues.", 200 if report["ready"] else 503)


@api_bp.get("/api/system")
def system():
    return success({"settings": get_store().get_settings(), "monitoring": get_camera_manager().statistics(), "cameras": get_camera_manager().list_cameras(), "health": get_health_service().check()})


@api_bp.get("/api/settings")
def get_settings():
    return success(get_store().get_settings())


@api_bp.put("/api/settings")
def update_settings():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return failure("A JSON object request body is required.")
    try:
        return success(get_store().update_settings(_validate_settings(payload)), "Settings saved.")
    except (ValueError, TypeError) as error:
        return failure(str(error))


@api_bp.get("/api/logs")
def logs():
    try:
        return success(get_store().list_events(request.args.get("limit", 100, type=int), request.args.get("category")))
    except (ValueError, TypeError) as error:
        return failure(str(error))


@api_bp.get("/api/alerts")
def alerts():
    return success(get_store().list_events(request.args.get("limit", 100, type=int), "alert"))


@api_bp.get("/api/ping")
def ping():
    return success({"message": "pong"})
