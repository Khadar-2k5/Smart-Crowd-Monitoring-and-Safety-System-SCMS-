"""Threshold and restricted-zone alert handling with incident evidence."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from backend.data_store import DataStore


class AlertManager:
    """Creates de-duplicated incidents and persists their metadata."""

    def __init__(self, store: DataStore, settings_provider: Callable[[], dict[str, Any]]) -> None:
        self.store = store
        self.settings_provider = settings_provider
        self._last_alert_at: dict[str, float] = {}

    def evaluate(self, camera_id: str, occupancy: int, zone_events: list[dict[str, Any]], save_evidence: Callable[[str], Path | None]) -> list[dict[str, Any]]:
        settings = self.settings_provider()
        candidates: list[tuple[str, str, dict[str, Any]]] = []
        threshold = int(settings["crowd_threshold"])
        if occupancy > threshold:
            candidates.append(("crowd_capacity", f"Crowd threshold exceeded: {occupancy}/{threshold} people", {"occupancy": occupancy, "threshold": threshold}))
        for event in zone_events:
            if event["type"] == "zone_capacity":
                candidates.append(("zone_capacity", f"{event['zone']} capacity exceeded: {event['occupancy']}/{event['threshold']}", event))
        alerts = []
        cooldown = max(1, int(settings["alert_cooldown_seconds"]))
        now = time.monotonic()
        for alert_type, message, payload in candidates:
            key = f"{camera_id}:{alert_type}:{payload.get('zone_id', '')}"
            if now - self._last_alert_at.get(key, 0) < cooldown:
                continue
            self._last_alert_at[key] = now
            evidence = save_evidence("alert") if settings.get("save_alert_screenshots", True) else None
            if evidence:
                payload = {**payload, "screenshot": evidence.name}
            event_id = self.store.log_event("alert", "WARNING", message, camera_id, payload)
            alerts.append({"id": event_id, "type": alert_type, "message": message, "camera_id": camera_id, "payload": payload})
        return alerts
