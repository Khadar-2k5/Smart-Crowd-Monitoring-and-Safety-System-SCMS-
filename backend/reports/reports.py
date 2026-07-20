"""CSV, JSON, text and PDF safety report generation."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.config import Config
from backend.data_store import DataStore
from backend.utils.helpers import utc_now


class ReportGenerator:
    """Produces self-contained reports from current telemetry and persisted history."""

    SUPPORTED_FORMATS = {"csv", "json", "txt", "pdf"}

    def __init__(self, store: DataStore, camera_manager, export_dir: Path | None = None) -> None:
        self.store = store
        self.camera_manager = camera_manager
        self.export_dir = export_dir or Config.EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def collect(self, camera_id: str | None = None) -> dict[str, Any]:
        try:
            statistics = self.camera_manager.statistics(camera_id)
        except KeyError:
            statistics = {
                "camera_id": camera_id,
                "camera_name": "Archived camera",
                "occupancy": 0,
                "tracking_count": 0,
                "fps": 0,
                "running": False,
                "analytics": {"history": []},
            }
        events = self.store.list_events(limit=1000, camera_id=camera_id)
        alerts = [event for event in events if event["category"] == "alert"]
        incidents = [event for event in events if event["level"] in {"WARNING", "ERROR"}]
        screenshots = [event for event in events if event["category"] == "screenshot"]
        earliest = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        analytics_history = self.store.analytics_history(camera_id, earliest, utc_now())
        return {"generated_at": utc_now(), "scope": camera_id or "all_cameras", "statistics": statistics, "analytics_history": analytics_history, "alerts": alerts, "incidents": incidents, "screenshots": screenshots, "events": events}

    def generate(self, report_format: str, camera_id: str | None = None) -> dict[str, Any]:
        report_format = report_format.lower()
        if report_format not in self.SUPPORTED_FORMATS:
            raise ValueError("format must be csv, json, txt, or pdf.")
        data = self.collect(camera_id)
        statistics = data.get("statistics", {})
        analytics_history = data.get("analytics_history", [])

        if "aggregate" in statistics:
            occupancy = statistics["aggregate"].get("occupancy", 0)
        else:
            occupancy = statistics.get("occupancy", 0)

        has_data = any([
            occupancy > 0,
            len(data.get("events", [])) > 0,
            len(data.get("alerts", [])) > 0,
            len(data.get("incidents", [])) > 0,
            len(data.get("screenshots", [])) > 0,
            len(analytics_history) > 0,
        ])

        if not has_data:
            raise ValueError(
                "Nothing to export. Start monitoring and generate some activity before creating a report."
            )

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_id = f"report_{uuid.uuid4().hex[:10]}"
        filename = f"smart_crowd_{stamp}_{report_id}.{report_format}"
        path = self.export_dir / filename
        {"csv": self._csv, "json": self._json, "txt": self._txt, "pdf": self._pdf}[report_format](path, data)
        summary = self._summary(data)
        report = {"id": report_id, "created_at": utc_now(), "format": report_format, "filename": filename, "summary": summary}
        self.store.add_report(report)
        return report

    @staticmethod
    def _summary(data: dict[str, Any]) -> dict[str, Any]:
        statistics = data["statistics"]

        if "aggregate" in statistics:
            active = statistics.get("active_cameras", 0)
        else:
            active = int(statistics.get("running", False))

        # Use the highest recorded occupancy from analytics history.
        history = data.get("analytics_history", [])

        if history:
            peak_occupancy = max(sample.get("occupancy", 0) for sample in history)
        else:
            if "aggregate" in statistics:
                peak_occupancy = statistics.get("aggregate", {}).get("occupancy", 0)
            else:
                peak_occupancy = statistics.get("occupancy", 0)

        return {
            "active_cameras": active,
            "current_occupancy": peak_occupancy,
            "alerts": len(data.get("alerts", [])),
            "incidents": len(data.get("incidents", [])),
            "screenshots": len(data.get("screenshots", [])),
        }    

    def _json(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _csv(self, path: Path, data: dict[str, Any]) -> None:
        with path.open("w", newline="", encoding="utf-8") as report_file:
            writer = csv.writer(report_file)
            writer.writerow(["Smart Crowd Monitoring & Safety Report"])
            writer.writerow(["Generated at", data["generated_at"]])
            writer.writerow([])
            writer.writerow(["Event ID", "Timestamp", "Category", "Level", "Camera", "Message", "Payload"])
            for event in data["events"]:
                writer.writerow([event["id"], event["created_at"], event["category"], event["level"], event["camera_id"] or "", event["message"], json.dumps(event["payload"])])
            writer.writerow([])
            writer.writerow(["Statistics JSON", json.dumps(data["statistics"])])
            writer.writerow([])
            writer.writerow(["Occupancy timestamp", "Camera", "Occupancy", "Tracking count", "FPS", "Density"])
            for sample in data["analytics_history"]:
                writer.writerow([sample["created_at"], sample["camera_id"], sample["occupancy"], sample["tracking_count"], sample["fps"], sample["density"]])

    def _txt(self, path: Path, data: dict[str, Any]) -> None:
        summary = self._summary(data)
        lines = ["SMART CROWD MONITORING & SAFETY REPORT", "=" * 48, f"Generated: {data['generated_at']}", f"Scope: {data['scope']}", "", "STATISTICS"]
        display_summary = {"Active Cameras": summary["active_cameras"],"Peak Occupancy": summary["current_occupancy"],"Alerts": summary["alerts"],"Incidents": summary["incidents"],"Screenshots": summary["screenshots"],}

        lines += [f"{key}: {value}" for key, value in display_summary.items()]
        lines += ["", "ALERTS & INCIDENTS"]
        lines += [f"[{event['created_at']}] {event['level']} {event['message']}" for event in data["incidents"]] or ["No incidents recorded."]
        lines += ["", "TRACKING AND CAMERA EVENTS"]
        lines += [f"[{event['created_at']}] {event['category']}: {event['message']}" for event in data["events"][:100]]
        path.write_text("\n".join(lines), encoding="utf-8")

    def _pdf(self, path: Path, data: dict[str, Any]) -> None:
        document = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
        styles = getSampleStyleSheet()
        story = [Paragraph("Smart Crowd Monitoring &amp; Safety Report", styles["Title"]), Paragraph(f"Generated: {data['generated_at']} &nbsp; | &nbsp; Scope: {data['scope']}", styles["Normal"]), Spacer(1, 0.35 * cm)]
        summary = self._summary(data)
        table_data = [["Metric", "Value"],["Active Cameras", summary["active_cameras"]],["Peak Occupancy", summary["current_occupancy"]],["Alerts", summary["alerts"]],["Incidents", summary["incidents"]],["Screenshots", summary["screenshots"]],]
        table = Table(table_data, colWidths=[9 * cm, 7 * cm])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#19324b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b9c5d0")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef4f8")]), ("PADDING", (0, 0), (-1, -1), 7)]))
        story += [Paragraph("Safety Summary", styles["Heading2"]), table, Spacer(1, 0.4 * cm), Paragraph("Occupancy Trend", styles["Heading2"]), self._occupancy_chart(data, 16 * cm, 5 * cm), Spacer(1, 0.35 * cm)]
        event_rows = [["Time", "Level", "Camera", "Incident"]]
        for event in data["incidents"][:18]:
            event_rows.append([event["created_at"].replace("T", " ")[:19], event["level"], event["camera_id"] or "—", event["message"]])
        if len(event_rows) == 1:
            event_rows.append(["—", "INFO", "—", "No alerts or errors recorded."])
        incidents = Table(event_rows, colWidths=[3.3 * cm, 2 * cm, 2.7 * cm, 8 * cm], repeatRows=1)
        incidents.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#19324b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5)]))
        story += [Paragraph("Alerts and Incidents", styles["Heading2"]), incidents]
        document.build(story)

    def _occupancy_chart(self, data: dict[str, Any], width: float, height: float) -> Table:
        """A compact vector chart rendered as a table cell, requiring no extra plotting dependency."""
        statistics = data["statistics"]
        cameras = statistics.get("cameras", [statistics])
        values: list[int] = []
        for camera in cameras:
            values.extend(sample["occupancy"] for sample in camera.get("analytics", {}).get("history", []))
        if not values:
            values.extend(sample["occupancy"] for sample in data.get("analytics_history", []))
        if not values:
            return Table([["No sampled occupancy data yet. Start monitoring to build the trend."]], colWidths=[width])
        from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
        drawing = Drawing(width, height)
        drawing.add(Line(25, 20, width - 10, 20, strokeColor=colors.grey))
        drawing.add(Line(25, 20, 25, height - 10, strokeColor=colors.grey))
        maximum = max(max(values), 1)
        points = []
        for index, value in enumerate(values[-80:]):
            x = 25 + (width - 40) * index / max(len(values[-80:]) - 1, 1)
            y = 20 + (height - 35) * value / maximum
            points.extend([x, y])
        drawing.add(PolyLine(points, strokeColor=colors.HexColor("#19a974"), strokeWidth=1.8))
        drawing.add(String(30, height - 10, f"Peak: {maximum}", fontSize=8, fillColor=colors.HexColor("#19324b")))
        return Table([[drawing]], colWidths=[width])
