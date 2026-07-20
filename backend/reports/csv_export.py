"""CSV report export compatibility interface."""

from pathlib import Path
from backend.reports.reports import ReportGenerator


def export_csv(generator: ReportGenerator, path: Path, data: dict) -> None:
    generator._csv(path, data)
