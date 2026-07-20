"""Streaming occupancy metrics used by the dashboard and reports."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from time import monotonic


class OccupancyAnalytics:
    def __init__(self, sample_interval_seconds: float = 5.0) -> None:
        self.sample_interval_seconds = max(1.0, float(sample_interval_seconds))
        self.reset()

    def reset(self) -> None:
        self.samples: deque[dict] = deque(maxlen=7200)
        self.maximum = 0
        self.total = 0
        self.frames = 0
        self.unique_ids: set[int] = set()
        self.last_sample_at = 0.0

    def update(self, occupancy: int, fps: float, detections: list[dict]) -> dict | None:
        self.maximum = max(self.maximum, occupancy)
        self.total += occupancy
        self.frames += 1
        self.unique_ids.update(d["id"] for d in detections if d["id"] is not None)
        now = monotonic()
        if now - self.last_sample_at < self.sample_interval_seconds:
            return None
        self.last_sample_at = now
        sample = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "occupancy": occupancy,
            "tracking_count": len([d for d in detections if d["id"] is not None]),
            "fps": round(fps, 1),
        }
        self.samples.append(sample)
        return sample

    def summary(self) -> dict:
        return {"current": self.samples[-1]["occupancy"] if self.samples else 0, "maximum": self.maximum, "average": round(self.total / self.frames, 2) if self.frames else 0, "peak": self.maximum, "unique_people": len(self.unique_ids), "history": list(self.samples)[-120:]}
