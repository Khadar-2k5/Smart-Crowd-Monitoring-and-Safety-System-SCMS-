"""Restricted polygon zones and a directed counting line."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np


@dataclass
class Zone:
    id: str
    name: str
    points: list[list[int]]
    alert_threshold: int | None = None
    occupants: set[int] = field(default_factory=set)
    entered_at: dict[int, float] = field(default_factory=dict)


class ZoneManager:
    """Tracks entry/exit and time spent in arbitrarily shaped polygon zones."""

    def __init__(self) -> None:
        self.zones: dict[str, Zone] = {}
        self.line: dict[str, list[int]] | None = None
        self._previous_side: dict[int, float] = {}
        self.in_count = 0
        self.out_count = 0
        self.counted_in: set[int] = set()
        self.counted_out: set[int] = set()

    def set_zones(self, zones: list[dict[str, Any]]) -> None:
        parsed: dict[str, Zone] = {}
        for zone_data in zones:
            points = zone_data.get("points", [])
            if len(points) < 3 or any(len(point) != 2 for point in points):
                raise ValueError("Every zone requires at least three [x, y] points.")
            zone_id = str(zone_data.get("id") or uuid.uuid4().hex[:10])
            parsed[zone_id] = Zone(
                id=zone_id, name=str(zone_data.get("name") or f"Zone {len(parsed) + 1}"),
                points=[[int(point[0]), int(point[1])] for point in points],
                alert_threshold=int(zone_data["alert_threshold"]) if zone_data.get("alert_threshold") is not None else None,
            )
        self.zones = parsed

    def set_line(self, line: dict[str, Any] | None) -> None:
        if line is None:
            self.line = None
            self._previous_side.clear()
            return
        start, end = line.get("start"), line.get("end")
        if not (isinstance(start, list) and isinstance(end, list) and len(start) == len(end) == 2):
            raise ValueError("Counting line requires start and end [x, y] coordinates.")
        self.line = {"start": [int(start[0]), int(start[1])], "end": [int(end[0]), int(end[1])]}
        self._previous_side.clear()

    def analyze(self, detections: list[dict[str, Any]]) -> dict[str, Any]:
        now = time.monotonic()
        events: list[dict[str, Any]] = []
        current_ids = {detection["id"] for detection in detections if detection["id"] is not None}
        for zone in self.zones.values():
            polygon = np.asarray(zone.points, dtype=np.int32)
            new_occupants: set[int] = set()
            for detection in detections:
                track_id = detection["id"]
                if track_id is None:
                    continue
                inside = cv2.pointPolygonTest(polygon, tuple(detection["center"]), False) >= 0
                if inside:
                    new_occupants.add(track_id)
                    if track_id not in zone.occupants:
                        zone.entered_at[track_id] = now
                        events.append({"type": "zone_entry", "zone_id": zone.id, "zone": zone.name, "track_id": track_id})
                elif track_id in zone.occupants:
                    elapsed = round(now - zone.entered_at.pop(track_id, now), 1)
                    events.append({"type": "zone_exit", "zone_id": zone.id, "zone": zone.name, "track_id": track_id, "seconds_inside": elapsed})
            vanished = zone.occupants - current_ids
            for track_id in vanished:
                zone.entered_at.pop(track_id, None)
            zone.occupants = new_occupants
            if zone.alert_threshold is not None and len(zone.occupants) > zone.alert_threshold:
                events.append({"type": "zone_capacity", "zone_id": zone.id, "zone": zone.name, "occupancy": len(zone.occupants), "threshold": zone.alert_threshold})
        self._analyze_line(detections, events)
        return {"events": events, "zones": self.summary(), "in_count": self.in_count, "out_count": self.out_count}

    def _analyze_line(self, detections: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
        if not self.line:
            return
        (x1, y1), (x2, y2) = self.line["start"], self.line["end"]
        for detection in detections:
            track_id = detection["id"]
            if track_id is None:
                continue
            x, y = detection["center"]
            side = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            previous = self._previous_side.get(track_id)
            if previous is not None and previous * side < 0:
                if previous < 0 < side and track_id not in self.counted_in:
                    self.in_count += 1
                    self.counted_in.add(track_id)
                    events.append({"type": "line_crossing", "direction": "IN", "track_id": track_id})
                elif previous > 0 > side and track_id not in self.counted_out:
                    self.out_count += 1
                    self.counted_out.add(track_id)
                    events.append({"type": "line_crossing", "direction": "OUT", "track_id": track_id})
            self._previous_side[track_id] = side

    def summary(self) -> list[dict[str, Any]]:
        return [{"id": zone.id, "name": zone.name, "points": zone.points, "occupancy": len(zone.occupants), "alert_threshold": zone.alert_threshold} for zone in self.zones.values()]

    def draw(self, frame) -> None:
        for zone in self.zones.values():
            polygon = np.asarray(zone.points, dtype=np.int32)
            cv2.polylines(frame, [polygon], True, (0, 75, 255), 2)
            x, y = zone.points[0]
            cv2.putText(frame, f"{zone.name}: {len(zone.occupants)}", (x, max(y - 8, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 75, 255), 2, cv2.LINE_AA)
        if self.line:
            start, end = tuple(self.line["start"]), tuple(self.line["end"])
            cv2.line(frame, start, end, (255, 110, 0), 3)
            cv2.putText(frame, f"IN {self.in_count} / OUT {self.out_count}", (start[0], max(start[1] - 10, 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 110, 0), 2, cv2.LINE_AA)
