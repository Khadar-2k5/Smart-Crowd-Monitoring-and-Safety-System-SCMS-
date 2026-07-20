"""Registry and lifecycle manager for concurrent camera pipelines."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from backend.config import Config
from backend.data_store import DataStore, get_store
from backend.detection.video_processor import VideoProcessor
from backend.utils.helpers import utc_now


class CameraManager:
    def __init__(self, store: DataStore, session_id: str = "system") -> None:
        self.store = store
        self.session_id = session_id
        self._processors: dict[str, VideoProcessor] = {}
        self._lock = threading.RLock()

    def start_camera(self, source: str | int, source_type: str = "webcam", name: str | None = None, camera_id: str | None = None) -> VideoProcessor:
        source_type = source_type.lower()
        if source_type not in {"webcam", "usb", "rtsp", "ip", "video"}:
            raise ValueError("source_type must be webcam, usb, rtsp, ip, or video.")
        if source_type in {"webcam", "usb"}:
            source = int(source)
        with self._lock:
            if camera_id and camera_id in self._processors:
                self._processors[camera_id].stop()
            active = sum(processor.running for processor in self._processors.values())
            if not camera_id and active >= Config.MAX_CAMERAS:
                raise RuntimeError(f"Maximum of {Config.MAX_CAMERAS} concurrent cameras reached.")
            camera_id = camera_id or f"cam_{uuid.uuid4().hex[:10]}"
            display_name = name or f"{source_type.upper()} Camera"
            processor = VideoProcessor(
                camera_id,
                display_name,
                source,
                source_type,
                self.store,
                self.store.get_settings,
                self._mark_inactive,
                self.session_id,
            )
            self._processors[camera_id] = processor
            camera = {"id": camera_id, "name": display_name, "source": source, "source_type": source_type, "created_at": utc_now(), "active": True}
            self.store.add_camera(camera)
        try:
            processor.start()
        except Exception:
            with self._lock:
                self._processors.pop(camera_id, None)
            self.store.set_camera_active(camera_id, False)
            raise
        return processor

    def get_processor(self, camera_id: str) -> VideoProcessor:
        with self._lock:
            processor = self._processors.get(camera_id)
        if not processor:
            raise KeyError(f"Camera '{camera_id}' is not active in this server session.")
        return processor

    def stop_camera(self, camera_id: str) -> None:
        processor = self.get_processor(camera_id)
        processor.stop()
        self.store.set_camera_active(camera_id, False)

    def _mark_inactive(self, camera_id: str) -> None:
        """Persist natural camera completion/failure without touching worker state."""
        self.store.set_camera_active(camera_id, False)

    def remove_camera(self, camera_id: str) -> bool:
        with self._lock:
            processor = self._processors.pop(camera_id, None)
        if processor:
            processor.stop()
        return self.store.delete_camera(camera_id)

    def statistics(self, camera_id: str | None = None) -> dict[str, Any]:
        if camera_id:
            return self.get_processor(camera_id).get_statistics()
        with self._lock:
            cameras = [processor.get_statistics() for processor in self._processors.values()]
        active = [camera for camera in cameras if camera["running"]]
        averages = [camera.get("analytics", {}).get("average", 0) for camera in cameras]
        return {
            "cameras": cameras,
            "active_cameras": len(active),
            "aggregate": {
                "occupancy": sum(camera["occupancy"] for camera in active),
                "tracking_count": sum(camera["tracking_count"] for camera in active),
                "average_occupancy": round(sum(averages) / len(averages), 2) if averages else 0,
                "max_occupancy": max((camera.get("analytics", {}).get("maximum", 0) for camera in cameras), default=0),
                "peak_occupancy": max((camera.get("analytics", {}).get("peak", 0) for camera in cameras), default=0),
                "alerts": self.store.count_events(category="alert"),
                "incidents": self.store.count_events(level="ERROR"),
            },
        }

    def list_cameras(self) -> list[dict[str, Any]]:
        persisted = {camera["id"]: camera for camera in self.store.list_cameras()}
        with self._lock:
            for camera_id, processor in self._processors.items():
                persisted.setdefault(camera_id, {"id": camera_id, "name": processor.name, "source": str(processor.source), "source_type": processor.source_type, "created_at": None})
                persisted[camera_id].update({"active": processor.running, "paused": processor.paused, "error": processor.error, "error_code": processor.error_code})
        return list(persisted.values())

    def stop_all(self) -> None:
        with self._lock:
            processors = list(self._processors.values())
        for processor in processors:
            processor.stop()


_managers: dict[str, CameraManager] = {}
_manager_lock = threading.Lock()


def get_camera_manager(session_id: str | None = None) -> CameraManager:
    from backend.session_manager import current_session_id
    identifier = session_id or current_session_id()
    with _manager_lock:
        if identifier not in _managers:
            _managers[identifier] = CameraManager(get_store(identifier), identifier)
        return _managers[identifier]


def stop_all_managers() -> None:
    with _manager_lock:
        managers = list(_managers.values())
    for manager in managers:
        manager.stop_all()


def discard_manager(session_id: str) -> None:
    with _manager_lock:
        manager = _managers.pop(session_id, None)
    if manager:
        manager.stop_all()
