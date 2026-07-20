"""Startup diagnostics and operational health checks."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from backend.camera_manager import CameraManager
from backend.config import Config
from backend.data_store import DataStore
from backend.utils.dependency_manager import dependency_status
from backend.utils.model_loader import get_yolo_model


class SystemHealthService:
    """Evaluates critical deployment prerequisites without opening camera devices."""

    def __init__(self, store: DataStore, camera_manager: CameraManager) -> None:
        self.store = store
        self.camera_manager = camera_manager
        self.model_loaded = False

    def check(self) -> dict[str, Any]:
        dependencies = dependency_status()
        missing = [name for name, installed in dependencies.items() if not installed]
        session_root = self.store.path.parent.parent if self.camera_manager.session_id != "system" else Config.STORAGE_ROOT
        folders = {
            name: self._folder_status(path)
            for name, path in {
                "uploads": session_root / "uploads",
                "screenshots": session_root / "screenshots",
                "exports": session_root / "exports",
                "logs": session_root / "logs",
                "data": session_root / "data",
            }.items()
        }
        model_available = Config.MODEL_PATH.is_file() and Config.MODEL_PATH.stat().st_size > 0
        configuration_ok, configuration_detail = self._configuration_status()
        components = [
            self._component("backend", "Backend service", True, "Flask API is responding."),
            self._component("dependencies", "Runtime dependencies", not missing, "All required packages are available." if not missing else f"Missing: {', '.join(missing)}."),
            self._component("storage", "Required folders", all(item["ready"] for item in folders.values()), "Application storage is writable." if all(item["ready"] for item in folders.values()) else "One or more application folders are unavailable."),
            self._component("model", "YOLOv8 model", model_available, "Model loaded." if self.model_loaded else "Model artifact is available and ready to load." if model_available else "models/yolov8n.pt is missing or empty."),
            self._component("configuration", "Configuration", configuration_ok, configuration_detail),
            self._component("cameras", "Camera service", True, f"Ready for up to {Config.MAX_CAMERAS} cameras; {self.camera_manager.statistics()['active_cameras']} active."),
        ]
        healthy = all(component["ready"] for component in components)
        return {
            "status": "healthy" if healthy else "unhealthy",
            "ready": healthy,
            "components": components,
            "folders": folders,
            "dependencies": dependencies,
            "monitoring": self.camera_manager.statistics(),
        }

    def initialize(self) -> dict[str, Any]:
        """Validate prerequisites and warm the shared YOLO engine for the UI startup flow."""
        report = self.check()
        if not report["ready"]:
            return report
        try:
            get_yolo_model()
            self.model_loaded = True
        except Exception:
            # The diagnostic surface deliberately exposes an actionable state,
            # while the exception itself remains in server logs.
            self.model_loaded = False
            report = self.check()
            for component in report["components"]:
                if component["id"] == "model":
                    component.update({"ready": False, "status": "critical", "detail": "The AI model could not be initialized. Review application logs and model compatibility."})
            report["status"] = "unhealthy"
            report["ready"] = False
            return report
        return self.check()

    @staticmethod
    def _folder_status(path: Path) -> dict[str, Any]:
        return {"path": str(path), "ready": path.is_dir() and os.access(path, os.W_OK)}

    @staticmethod
    def _component(component_id: str, title: str, ready: bool, detail: str) -> dict[str, Any]:
        return {"id": component_id, "title": title, "ready": ready, "status": "ready" if ready else "critical", "detail": detail}

    @staticmethod
    def _configuration_status() -> tuple[bool, str]:
        valid = (
            0.05 <= Config.DEFAULT_CONFIDENCE <= 0.95
            and Config.DEFAULT_CROWD_THRESHOLD > 0
            and Config.DEFAULT_TARGET_INFERENCE_FPS > 0
            and Config.MAX_CAMERAS > 0
        )
        return (valid, "Runtime settings are valid." if valid else "One or more environment configuration values are invalid.")


_health_services: dict[str, SystemHealthService] = {}
_health_lock = threading.Lock()


def get_health_service() -> SystemHealthService:
    from backend.session_manager import current_session_id
    identifier = current_session_id()
    with _health_lock:
        if identifier not in _health_services:
            from backend.camera_manager import get_camera_manager
            from backend.data_store import get_store
            _health_services[identifier] = SystemHealthService(get_store(identifier), get_camera_manager(identifier))
        return _health_services[identifier]
