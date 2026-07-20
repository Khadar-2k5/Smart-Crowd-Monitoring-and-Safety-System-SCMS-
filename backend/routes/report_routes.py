"""Report generation and secure download REST endpoints."""

from pathlib import Path

from flask import Blueprint, request, send_from_directory

from backend.camera_manager import get_camera_manager
from backend.config import Config
from backend.data_store import get_store
from backend.reports import ReportGenerator
from backend.utils.helpers import failure, success
from backend.utils.logger import logger
from backend.session_manager import current_session_id, session_path

report_bp = Blueprint("reports", __name__)


def _reports() -> ReportGenerator:
    return ReportGenerator(get_store(), get_camera_manager(), session_path(current_session_id(), "exports"))


@report_bp.get("/api/reports")
def list_reports():
    return success(get_store().list_reports())


@report_bp.post("/api/reports/generate")
def generate_report():
    payload = request.get_json(silent=True) or {}
    try:
        report = _reports().generate(str(payload.get("format", "pdf")), payload.get("camera_id") or None)
        report["download_url"] = f"/api/reports/download/{report['filename']}"
        return success(report, "Report generated.", 201)
    except ValueError as error:
        return failure(str(error))
    except KeyError as error:
        return failure(str(error), 404)
    except Exception:
        logger.exception("Report generation failed")
        return failure("Report generation failed. Review application logs and try again.", 500)


@report_bp.get("/api/reports/download/<path:filename>")
def download_report(filename: str):
    safe_name = Path(filename).name
    export_dir = session_path(current_session_id(), "exports")
    if not (export_dir / safe_name).exists():
        return failure("Report was not found.", 404)
    return send_from_directory(export_dir, safe_name, as_attachment=True)
