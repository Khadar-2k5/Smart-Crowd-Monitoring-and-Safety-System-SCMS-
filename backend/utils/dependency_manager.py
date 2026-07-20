"""Non-mutating dependency checks for deployment diagnostics."""

from __future__ import annotations

import importlib.util
import sys

REQUIRED_PACKAGES = ("flask", "cv2", "numpy", "pandas", "ultralytics", "reportlab", "supervision")


def check_python_version() -> bool:
    if sys.version_info < (3, 10):
        raise RuntimeError(f"Python 3.10+ is required; found {sys.version_info.major}.{sys.version_info.minor}.")
    return True


def dependency_status() -> dict[str, bool]:
    """Return installed state without modifying the Python environment."""
    return {package: importlib.util.find_spec(package) is not None for package in REQUIRED_PACKAGES}


def missing_dependencies() -> list[str]:
    return [package for package, installed in dependency_status().items() if not installed]


def verify_dependencies() -> dict[str, list[str]]:
    """Validate runtime requirements and raise a clear error if any are absent."""
    check_python_version()
    status = dependency_status()
    missing = [package for package, installed in status.items() if not installed]
    if missing:
        raise RuntimeError("Missing dependencies: " + ", ".join(missing) + ". Run: pip install -r requirements.txt")
    return {"already_present": [package for package, installed in status.items() if installed], "missing": []}
