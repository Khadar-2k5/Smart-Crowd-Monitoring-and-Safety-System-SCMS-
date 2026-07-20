"""JSON report export compatibility interface."""

from pathlib import Path
from backend.reports.reports import ReportGenerator


def export_json(generator: ReportGenerator, path: Path, data: dict) -> None:
    generator._json(path, data)
