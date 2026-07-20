"""YOLOv8 person detection and ByteTrack identity tracking."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

import cv2
import numpy as np

from backend.utils.model_loader import run_inference


class PersonDetector:
    """Runs YOLOv8 with its ByteTrack integration and retains track histories."""

    PERSON_CLASS_ID = 0

    def __init__(self, confidence: float = 0.45) -> None:
        try:
            import supervision as sv
        except ImportError as error:
            raise RuntimeError("Supervision is not installed. Run: pip install -r requirements.txt") from error
        self.supervision = sv
        self.confidence = self._clamp_confidence(confidence)
        self.tracker = sv.ByteTrack(
            track_activation_threshold=self.confidence,
            lost_track_buffer=45,
            minimum_matching_threshold=0.8,
        )
        self.previous_time = time.perf_counter()
        self.fps = 0.0
        self.track_history: dict[int, deque[tuple[int, int]]] = defaultdict(lambda: deque(maxlen=40))
        self._last_seen: dict[int, int] = {}
        self._frame_number = 0

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        return max(0.05, min(0.95, float(value)))

    def set_confidence(self, confidence: float) -> None:
        self.confidence = self._clamp_confidence(confidence)

    def reset_tracking(self) -> None:
        self.track_history.clear()
        self._last_seen.clear()
        if hasattr(self.tracker, "reset"):
            self.tracker.reset()
        else:
            self.tracker = self.supervision.ByteTrack(
                track_activation_threshold=self.confidence,
                lost_track_buffer=45,
                minimum_matching_threshold=0.8,
            )

    def _calculate_fps(self) -> float:
        now = time.perf_counter()
        duration = max(now - self.previous_time, 0.0001)
        instant_fps = 1.0 / duration
        self.fps = instant_fps if not self.fps else self.fps * 0.85 + instant_fps * 0.15
        self.previous_time = now
        return round(self.fps, 1)

    def process_frame(self, frame) -> dict[str, Any]:
        """Return an annotated frame and stable per-person ByteTrack detections."""
        results = run_inference(frame, self.confidence)
        annotated = frame.copy()
        detections: list[dict[str, Any]] = []
        if results:
            # Supervision's ByteTrack instance is deliberately per camera.
            # It preserves identities without replicating the YOLO model in RAM.
            raw_detections = self.supervision.Detections.from_ultralytics(results[0])
            tracked = self.tracker.update_with_detections(raw_detections)
            scores = tracked.confidence if tracked.confidence is not None else np.zeros(len(tracked))
            track_ids = tracked.tracker_id if tracked.tracker_id is not None else [-1] * len(tracked)
            for box, score, track_id in zip(tracked.xyxy.astype(int), scores, track_ids):
                x1, y1, x2, y2 = map(int, box.tolist())
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                stable_id = int(track_id)
                if stable_id >= 0:
                    self.track_history[stable_id].append(center)
                    self._last_seen[stable_id] = self._frame_number
                detection = {
                    "id": stable_id if stable_id >= 0 else None,
                    "confidence": round(float(score), 3),
                    "bbox": [x1, y1, x2, y2],
                    "center": [center[0], center[1]],
                }
                detections.append(detection)
                self._draw_detection(annotated, detection)
        self._frame_number += 1
        self._prune_track_history()
        return {"frame": annotated, "detections": detections, "count": len(detections), "fps": self._calculate_fps(), "track_history": self.track_history}

    def _prune_track_history(self) -> None:
        expired = [track_id for track_id, frame_number in self._last_seen.items() if self._frame_number - frame_number > 180]
        for track_id in expired:
            self._last_seen.pop(track_id, None)
            self.track_history.pop(track_id, None)

    def _draw_detection(self, frame, detection: dict[str, Any]) -> None:
        x1, y1, x2, y2 = detection["bbox"]
        track_id = detection["id"]
        label = f"ID {track_id if track_id is not None else '?'}  {detection['confidence']:.0%}"
        color = (85, 225, 135) if track_id is not None else (0, 196, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
        top = max(y1 - label_size[1] - baseline - 8, 0)
        cv2.rectangle(frame, (x1, top), (x1 + label_size[0] + 8, y1), color, -1)
        cv2.putText(frame, label, (x1 + 4, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (17, 25, 39), 1, cv2.LINE_AA)
        history = self.track_history.get(track_id)
        if history and len(history) > 1:
            cv2.polylines(frame, [np.array(history, dtype="int32")], False, color, 1)
