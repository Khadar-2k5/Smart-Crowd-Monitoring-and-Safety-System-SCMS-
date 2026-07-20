"""Historical occupancy analytics and graph data exports."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, request

from backend.data_store import get_store
from backend.utils.helpers import failure, success

analytics_bp = Blueprint("analytics", __name__)

RANGE_TO_DELTA = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _window() -> tuple[str, str]:
    range_key = request.args.get("range", "1h")
    now = datetime.now(timezone.utc)
    if range_key == "custom":
        try:
            start = datetime.fromisoformat(request.args["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(request.args["end"].replace("Z", "+00:00"))
        except (KeyError, ValueError) as error:
            raise ValueError("Custom ranges require valid ISO-8601 start and end timestamps.") from error
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Custom start must be before end and both timestamps must include a timezone.")
        if end - start > timedelta(days=7):
            raise ValueError("Custom analytics range cannot exceed seven days.")
    elif range_key in RANGE_TO_DELTA:
        end, start = now, now - RANGE_TO_DELTA[range_key]
    else:
        raise ValueError("Unsupported range. Use 5m, 15m, 30m, 1h, 6h, 12h, 24h, 7d, or custom.")
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


@analytics_bp.get("/api/analytics/history")
def analytics_history():
    try:
        start_at, end_at = _window()
        camera_id = request.args.get("camera_id") or None
        samples = get_store().analytics_history(camera_id, start_at, end_at)
        return success({"camera_id": camera_id, "start": start_at, "end": end_at, "samples": samples})
    except ValueError as error:
        return failure(str(error))


@analytics_bp.get("/api/analytics/export")
def export_analytics():
    try:
        start_at, end_at = _window()
        samples = get_store().analytics_history(request.args.get("camera_id") or None, start_at, end_at)
        export_format = request.args.get("format", "csv").lower()
        if export_format == "json":
            return Response(json.dumps(samples, indent=2), mimetype="application/json", headers={"Content-Disposition": "attachment; filename=occupancy_history.json"})
        if export_format != "csv":
            return failure("format must be csv or json.")
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=["created_at", "camera_id", "occupancy", "tracking_count", "fps", "density"])
        writer.writeheader()
        writer.writerows(samples)
        return Response(buffer.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=occupancy_history.csv"})
    except ValueError as error:
        return failure(str(error))
