"""Saved camera management endpoints."""

from flask import Blueprint

from backend.camera_manager import get_camera_manager
from backend.utils.helpers import failure, success
from backend.utils.logger import logger

camera_bp = Blueprint("cameras", __name__)


@camera_bp.get("/api/cameras")
def list_cameras():
    return success(get_camera_manager().list_cameras())


@camera_bp.delete("/api/cameras/<camera_id>")
def delete_camera(camera_id: str):
    try:
        if not get_camera_manager().remove_camera(camera_id):
            return failure("Camera was not found.", 404)
        return success(message="Camera registration removed.")
    except Exception:
        logger.exception("Unable to remove camera %s", camera_id)
        return failure("The camera registration could not be removed. Review application logs.", 500)
