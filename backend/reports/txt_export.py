"""Text report export compatibility interface."""

from pathlib import Path
from backend.reports.reports import ReportGenerator


def export_txt(generator: ReportGenerator, path: Path, data: dict) -> None:
    generator._txt(path, data)
