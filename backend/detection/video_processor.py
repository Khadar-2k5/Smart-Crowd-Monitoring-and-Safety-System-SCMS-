"""Threaded single-camera pipeline: capture, detection, analytics and rendering."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import cv2

from backend.alerts.alert_manager import AlertManager
from backend.analytics.heatmap import Heatmap
from backend.analytics.occupancy import OccupancyAnalytics
from backend.config import Config
from backend.data_store import DataStore
from backend.detection.detector import PersonDetector
from backend.detection.frame_encoder import FrameEncoder
from backend.detection.zone_manager import ZoneManager
from backend.utils.helpers import utc_now
from backend.utils.logger import logger


class VideoProcessor:
    """Owns all capture resources and state for one camera source."""

    def __init__(
        self,
        camera_id: str,
        name: str,
        source: str | int,
        source_type: str,
        store: DataStore,
        settings_provider: Callable[[], dict[str, Any]],
        on_stopped: Callable[[str], None] | None = None,
        session_id: str = "system",
    ) -> None:
        self.camera_id, self.name = camera_id, name
        self.source, self.source_type = source, source_type
        self.store, self.settings_provider = store, settings_provider
        self.session_id = session_id
        self.detector = PersonDetector(settings_provider()["confidence_threshold"])
        self.zone_manager = ZoneManager()
        self.heatmap = Heatmap()
        self.analytics = OccupancyAnalytics(Config.ANALYTICS_SAMPLE_SECONDS)
        self.alert_manager = AlertManager(store, settings_provider)
        self.capture = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.paused = False
        self.error: str | None = None
        self.error_code: str | None = None
        self._lock = threading.RLock()
        self._frame_ready = threading.Condition(self._lock)
        self._frame = None
        self._heatmap_frame = None
        self._encoded_live: bytes | None = None
        self._encoded_heatmap: bytes | None = None
        self._frame_sequence = 0
        self._started_at: float | None = None
        self._last_inference_at = 0.0
        self._on_stopped = on_stopped
        self._last_stats: dict[str, Any] = self._empty_stats()
        self._recent_alerts: list[dict[str, Any]] = []

    def _empty_stats(self) -> dict[str, Any]:
        return {"camera_id": self.camera_id, "camera_name": self.name, "source_type": self.source_type, "occupancy": 0, "tracking_count": 0, "fps": 0.0, "runtime_seconds": 0, "running": False, "paused": False, "error": None, "error_code": None, "people_entered": 0, "people_exited": 0, "zones": [], "density": "Low", "alerts": []}

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
        capture_source: str | int = self.source
        if self.source_type in {"webcam", "usb"}:
            capture_source = int(self.source)
        # Open webcam/video with the appropriate backend
        if self.source_type == "video":
            capture = cv2.VideoCapture(str(capture_source), cv2.CAP_FFMPEG)
        else:
            capture = cv2.VideoCapture(capture_source)

        if not capture.isOpened():
            capture.release()
            code = "camera_not_found" if self.source_type in {"webcam", "usb"} else "stream_unavailable"
            raise RuntimeError(
                f"Unable to open source: {capture_source} ({code})."
            )

        # ----- Render diagnostics -----
        logger.info("=" * 60)
        logger.info("Camera ID      : %s", self.camera_id)
        logger.info("Source Type    : %s", self.source_type)
        logger.info("Capture Source : %s", capture_source)
        logger.info("Opened         : %s", capture.isOpened())
        logger.info("Frame Count    : %s", capture.get(cv2.CAP_PROP_FRAME_COUNT))
        logger.info("Width          : %s", capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        logger.info("Height         : %s", capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("=" * 60)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAMERA_FRAME_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAMERA_FRAME_HEIGHT)
        with self._lock:
            self.capture = capture
            self.running, self.paused, self.error, self.error_code = True, False, None, None
            self._started_at = time.monotonic()
            self.thread = threading.Thread(target=self._processing_loop, name=f"camera-{self.camera_id}", daemon=True)
            self.thread.start()
        self.store.log_event("camera", "INFO", f"Monitoring started for {self.name}", self.camera_id, {"source_type": self.source_type})

    def _processing_loop(self) -> None:
        try:
            while self.running:
                if self.paused:
                    time.sleep(0.08)
                    continue
                capture = self.capture
                if capture is None:
                    break
                success, frame = capture.read()
                # Retry reading the first frame (helps on slower cloud instances)
                success = False
                frame = None

                for attempt in range(10):
                    success, frame = capture.read()

                    if success:
                        break

                    logger.warning(
                        "Frame read failed (%d/10) for %s",
                        attempt + 1,
                        self.camera_id,
                    )

                    time.sleep(0.2)

                if not success:
                    logger.error("Unable to read any frame from source: %s", self.source)

                    if not self.running:
                        break

                    if self.source_type == "video":
                        self.error_code = "video_read_failed"
                        self.error = "Unable to decode the uploaded video."
                        self.store.log_event(
                            "camera",
                            "ERROR",
                            self.error,
                            self.camera_id,
                        )
                    else:
                        self.error_code = "stream_lost"
                        self.error = "The camera stream was lost."
                        self.store.log_event(
                            "camera",
                            "ERROR",
                            self.error,
                            self.camera_id,
                        )

                    break
                settings = self.settings_provider()
                target_fps = max(1, int(settings["target_inference_fps"]))
                remaining = (1 / target_fps) - (time.monotonic() - self._last_inference_at)
                if remaining > 0:
                    time.sleep(min(remaining, 0.08))
                self._last_inference_at = time.monotonic()
                self.detector.set_confidence(settings["confidence_threshold"])
                result = self.detector.process_frame(frame)
                analysis = self.zone_manager.analyze(result["detections"])
                self.heatmap.update(frame, result["detections"])
                rendered = result["frame"]
                self.zone_manager.draw(rendered)
                self._draw_overlay(rendered, result["count"], result["fps"])
                sample = self.analytics.update(result["count"], result["fps"], result["detections"])
                for zone_event in analysis["events"]:
                    if zone_event["type"] in {"zone_entry", "zone_exit", "line_crossing"}:
                        self.store.log_event("tracking", "INFO", zone_event["type"], self.camera_id, zone_event)
                # Make the current annotated frame available to the alert callback,
                # so automatic evidence always belongs to the triggering frame.
                with self._lock:
                    self._frame = rendered
                alerts = self.alert_manager.evaluate(
                    self.camera_id,
                    result["count"],
                    analysis["events"],
                    lambda reason: self._save_snapshot(reason, rendered),
                )
                stats = self._build_stats(result, analysis, alerts, settings)
                if sample:
                    try:
                        self.store.record_occupancy_sample(
                            self.camera_id,
                            sample["occupancy"],
                            sample["tracking_count"],
                            sample["fps"],
                            stats["density"],
                            sample["time"],
                        )
                    except Exception:
                        logger.exception("Occupancy sample persistence failed for %s", self.camera_id)
                with self._frame_ready:
                    self._frame = rendered
                    self._heatmap_frame = self.heatmap.render(frame, float(settings["heatmap_opacity"]))
                    self._encoded_live = FrameEncoder.encode(rendered)
                    self._encoded_heatmap = FrameEncoder.encode(self._heatmap_frame)
                    self._frame_sequence += 1
                    self._recent_alerts = (alerts + self._recent_alerts)[:20]
                    self._last_stats = stats
                    self._frame_ready.notify_all()
        except Exception as error:  # Keep camera failure isolated from the server.
            logger.exception("Camera processing failed for %s", self.camera_id)
            self.error_code = "processing_failure"
            self.error = "The camera processing service stopped unexpectedly."
            self.store.log_event("error", "ERROR", "Processor failure", self.camera_id, {"exception": str(error)})
        finally:
            with self._lock:
                self.running = False
                if self.capture is not None:
                    self.capture.release()
                    self.capture = None
                self._last_stats["running"] = False
                self._last_stats["error"] = self.error
                self._last_stats["error_code"] = self.error_code
                self._frame_ready.notify_all()
            if self._on_stopped:
                try:
                    self._on_stopped(self.camera_id)
                except Exception:
                    logger.exception("Could not persist stopped state for %s", self.camera_id)

    def _build_stats(
        self,
        result: dict[str, Any],
        analysis: dict[str, Any],
        alerts: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = int(time.monotonic() - self._started_at) if self._started_at else 0
        occupancy = result["count"]
        threshold = int(settings["crowd_threshold"])
        density = "Critical" if occupancy > threshold else "High" if occupancy > threshold * 0.7 else "Moderate" if occupancy > threshold * 0.35 else "Low"
        return {"camera_id": self.camera_id, "camera_name": self.name, "source_type": self.source_type, "occupancy": occupancy, "tracking_count": len([d for d in result["detections"] if d["id"] is not None]), "fps": result["fps"], "runtime_seconds": runtime, "running": self.running, "paused": self.paused, "error": self.error, "error_code": self.error_code, "people_entered": analysis["in_count"], "people_exited": analysis["out_count"], "zones": analysis["zones"], "density": density, "alerts": alerts, "detections": result["detections"], "analytics": self.analytics.summary()}

    def _draw_overlay(self, frame, occupancy: int, fps: float) -> None:
        cv2.rectangle(frame, (14, 14), (295, 105), (18, 26, 43), -1)
        cv2.rectangle(frame, (14, 14), (295, 105), (70, 210, 170), 2)
        cv2.putText(frame, "SMART CROWD MONITORING", (26, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 244, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"OCCUPANCY: {occupancy}", (26, 67), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (85, 225, 135), 2, cv2.LINE_AA)
        cv2.putText(frame, f"FPS: {fps:.1f}", (26, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 205, 85), 2, cv2.LINE_AA)

    def pause(self) -> None:
        with self._lock:
            if not self.running:
                raise RuntimeError("Camera is not running.")
            self.paused = True
            self._last_stats["paused"] = True
        self.store.log_event("camera", "INFO", f"Monitoring paused for {self.name}", self.camera_id)

    def resume(self) -> None:
        with self._lock:
            if not self.running:
                raise RuntimeError("Camera is not running.")
            self.paused = False
            self._last_stats["paused"] = False
        self.store.log_event("camera", "INFO", f"Monitoring resumed for {self.name}", self.camera_id)

    def stop(self) -> None:
        with self._lock:
            was_running = self.running
            self.running, self.paused = False, False
            capture, thread = self.capture, self.thread
        if capture is not None:
            capture.release()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)
        if was_running:
            self.store.log_event("camera", "INFO", f"Monitoring stopped for {self.name}", self.camera_id)

    def _save_snapshot(self, reason: str, frame=None) -> Path | None:
        if frame is None:
            with self._lock:
                frame = self._frame.copy() if self._frame is not None else None
        if frame is None:
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{self.camera_id}_{reason}_{timestamp}.jpg"
        from backend.session_manager import session_path
        path = session_path(self.session_id, "screenshots") / filename if self.session_id != "system" else Config.SCREENSHOT_DIR / filename
        if not cv2.imwrite(str(path), frame.copy()):
            return None
        self.store.log_event("screenshot", "INFO", f"{reason.title()} screenshot saved", self.camera_id, {"filename": filename, "reason": reason, "created_at": utc_now()})
        return path

    def snapshot(self, reason: str = "manual") -> Path:
        saved = self._save_snapshot(reason)
        if not saved:
            raise RuntimeError("No processed video frame is available to capture.")
        return saved

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            values = dict(self._last_stats)
            values["running"], values["paused"], values["error"] = self.running, self.paused, self.error
            values["error_code"] = self.error_code
            if self._started_at and self.running:
                values["runtime_seconds"] = int(time.monotonic() - self._started_at)
            values["alerts"] = list(self._recent_alerts)
            return values

    def get_frame(self, heatmap: bool = False):
        with self._lock:
            frame = self._heatmap_frame if heatmap else self._frame
            return frame.copy() if frame is not None else None

    def generate_frames(self, heatmap: bool = False):
        last_sequence = -1
        while True:
            with self._frame_ready:
                self._frame_ready.wait_for(
                    lambda: self._frame_sequence != last_sequence or not self.running,
                    timeout=5,
                )
                encoded = self._encoded_heatmap if heatmap else self._encoded_live
                is_running = self.running
                last_sequence = self._frame_sequence
            if encoded:
                yield FrameEncoder.mjpeg(encoded)
            elif not is_running:
                break

    def set_zones(self, zones: list[dict[str, Any]]) -> None:
        with self._lock:
            self.zone_manager.set_zones(zones)
        self.store.log_event("configuration", "INFO", "Restricted zones updated", self.camera_id, {"zones": self.zone_manager.summary()})

    def set_counting_line(self, line: dict[str, Any] | None) -> None:
        with self._lock:
            self.zone_manager.set_line(line)
        self.store.log_event("configuration", "INFO", "Counting line updated", self.camera_id, {"line": line})
