"""Camera and live-monitoring REST endpoints."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, request, send_from_directory

from backend.camera_manager import get_camera_manager
from backend.config import Config
from backend.utils.helpers import failure, success, unique_filename
from backend.utils.logger import logger
from backend.session_manager import current_session_id, session_path

monitoring_bp = Blueprint("monitoring", __name__)


def _payload() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object request body is required.")
    return data


def _source_for(payload: dict) -> str | int:
    source_type = str(payload.get("source_type", "webcam")).lower()
    source = payload.get("source", 0)
    if source_type in {"webcam", "usb"}:
        return int(source)
    if source_type == "video":
        filename = Path(str(source)).name
        path = session_path(current_session_id(), "uploads") / filename
        if not path.exists():
            raise ValueError("Uploaded video was not found. Upload it before starting analysis.")
        return str(path)
    if source_type in {"rtsp", "ip"}:
        source = str(source).strip()
        if not source.startswith(("rtsp://", "http://", "https://")):
            raise ValueError("RTSP/IP camera source must begin with rtsp://, http://, or https://.")
        return source
    raise ValueError("Unsupported source type.")


@monitoring_bp.post("/api/monitoring/upload")
def upload_video():
    uploaded = request.files.get("video")
    if uploaded is None or not uploaded.filename:
        return failure("Select a video file to upload.")
    try:
        filename = unique_filename(uploaded.filename)
        destination = session_path(current_session_id(), "uploads") / filename
        uploaded.save(destination)
        return success({"filename": filename, "source": filename, "size_bytes": destination.stat().st_size}, "Video uploaded successfully.", 201)
    except ValueError as error:
        return failure(str(error))
    except Exception:
        logger.exception("Video upload failed")
        return failure("The uploaded video could not be saved. Check storage availability and try again.", 500)


@monitoring_bp.post("/api/monitoring/start")
@monitoring_bp.post("/api/cameras/start")
def start_monitoring():
    try:
        payload = _payload()
        processor = get_camera_manager().start_camera(
            source=_source_for(payload), source_type=str(payload.get("source_type", "webcam")),
            name=str(payload.get("name") or "").strip() or None, camera_id=payload.get("camera_id"),
        )
        return success(processor.get_statistics(), "Monitoring started.", 201)
    except (ValueError, TypeError) as error:
        return failure(str(error))
    except RuntimeError as error:
        message = str(error)
        code = "camera_start_failed"
        lowered = message.lower()
        if "busy" in lowered:
            code = "camera_busy"
        elif "not found" in lowered or "not_found" in lowered or "not available" in lowered or "unavailable" in lowered:
            code = "camera_not_found"
        elif "permission" in lowered:
            code = "permission_denied"
        return failure(message, 503, {"code": code})
    except Exception:
        logger.exception("Camera startup failed")
        return failure("The camera could not be started. Verify the source and review application logs.", 500)


@monitoring_bp.post("/api/monitoring/<camera_id>/<action>")
def camera_action(camera_id: str, action: str):
    if action not in {"stop", "pause", "resume"}:
        return failure("Unsupported monitoring action.", 404)
    try:
        manager = get_camera_manager()
        processor = manager.get_processor(camera_id)
        if action == "stop":
            manager.stop_camera(camera_id)
        else:
            getattr(processor, action)()
        return success(processor.get_statistics(), f"Monitoring {action}d." if action != "stop" else "Monitoring stopped.")
    except KeyError as error:
        return failure(str(error), 404)
    except RuntimeError as error:
        return failure(str(error), 409)


@monitoring_bp.get("/api/monitoring/statistics")
def statistics():
    camera_id = request.args.get("camera_id")
    try:
        return success(get_camera_manager().statistics(camera_id))
    except KeyError as error:
        return failure(str(error), 404)


@monitoring_bp.get("/api/statistics")
def legacy_statistics():
    return statistics()


@monitoring_bp.get("/video_feed/<camera_id>")
def video_feed(camera_id: str):
    try:
        processor = get_camera_manager().get_processor(camera_id)
        heatmap = request.args.get("mode") == "heatmap"
        return Response(processor.generate_frames(heatmap=heatmap), mimetype="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})
    except KeyError:
        return Response("Camera not found", status=404, mimetype="text/plain")


@monitoring_bp.post("/api/monitoring/<camera_id>/snapshot")
def snapshot(camera_id: str):
    try:
        path = get_camera_manager().get_processor(camera_id).snapshot()
        return success({"filename": path.name, "url": f"/api/screenshots/{path.name}"}, "Screenshot saved.", 201)
    except KeyError as error:
        return failure(str(error), 404)
    except RuntimeError as error:
        return failure(str(error), 409)


@monitoring_bp.get("/api/screenshots/<path:filename>")
def screenshot_file(filename: str):
    return send_from_directory(session_path(current_session_id(), "screenshots"), Path(filename).name, as_attachment=False)


@monitoring_bp.post("/api/monitoring/<camera_id>/zones")
def configure_zones(camera_id: str):
    try:
        zones = _payload().get("zones", [])
        if not isinstance(zones, list):
            raise ValueError("zones must be an array.")
        processor = get_camera_manager().get_processor(camera_id)
        processor.set_zones(zones)
        return success({"zones": processor.get_statistics()["zones"]}, "Restricted zones updated.")
    except KeyError as error:
        return failure(str(error), 404)
    except ValueError as error:
        return failure(str(error))


@monitoring_bp.post("/api/monitoring/<camera_id>/counting-line")
def configure_counting_line(camera_id: str):
    try:
        line = _payload().get("line")
        get_camera_manager().get_processor(camera_id).set_counting_line(line)
        return success({"line": line}, "Counting line updated.")
    except KeyError as error:
        return failure(str(error), 404)
    except ValueError as error:
        return failure(str(error))
