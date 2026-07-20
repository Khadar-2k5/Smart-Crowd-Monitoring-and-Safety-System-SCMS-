"""SQLite persistence for settings, camera registrations, logs and reports."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from backend.config import Config
from backend.utils.helpers import utc_now
from backend.utils.logger import logger

DEFAULT_SETTINGS = {
    "confidence_threshold": Config.DEFAULT_CONFIDENCE,
    "crowd_threshold": Config.DEFAULT_CROWD_THRESHOLD,
    "alert_cooldown_seconds": Config.DEFAULT_ALERT_COOLDOWN_SECONDS,
    "theme": "dark",
    "save_alert_screenshots": True,
    "heatmap_opacity": 0.45,
    "target_inference_fps": Config.DEFAULT_TARGET_INFERENCE_FPS,
}


class DataStore:
    """A compact, thread-safe repository around the application SQLite database."""

    def __init__(self, database_path=None) -> None:
        Config.create_directories()
        self.path = database_path or Config.DATABASE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._settings_cache: dict[str, Any] = {}
        self._sample_writes = 0
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
          category TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL,
          camera_id TEXT, payload TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS cameras (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
          source_type TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, format TEXT NOT NULL,
          filename TEXT NOT NULL, summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS occupancy_samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
          camera_id TEXT NOT NULL, occupancy INTEGER NOT NULL,
          tracking_count INTEGER NOT NULL, fps REAL NOT NULL, density TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_occupancy_samples_camera_time
          ON occupancy_samples(camera_id, created_at);
        """
        with self._lock, self.connection() as connection:
            connection.executescript(schema)
            for key, value in DEFAULT_SETTINGS.items():
                connection.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
            self._settings_cache = DEFAULT_SETTINGS.copy()
            self._settings_cache.update({row["key"]: json.loads(row["value"]) for row in rows})
            # ---------------------------------------------------
            # Reset session data on every application startup
            # ---------------------------------------------------
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM cameras")
            connection.execute("DELETE FROM reports")
            connection.execute("DELETE FROM occupancy_samples")

            connection.execute("DELETE FROM sqlite_sequence WHERE name='events'")
            connection.execute("DELETE FROM sqlite_sequence WHERE name='reports'")
            connection.execute("DELETE FROM sqlite_sequence WHERE name='occupancy_samples'")        

    def get_settings(self) -> dict[str, Any]:
        """Return the in-process cache; frame workers must never query SQLite."""
        with self._lock:
            return self._settings_cache.copy()

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        unknown = set(updates) - set(DEFAULT_SETTINGS)
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        with self._lock, self.connection() as connection:
            for key, value in updates.items():
                connection.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)),
                )
            self._settings_cache.update(updates)
            return self._settings_cache.copy()

    def log_event(self, category: str, level: str, message: str, camera_id: str | None = None, payload: dict[str, Any] | None = None) -> int:
        with self._lock, self.connection() as connection:
            cursor = connection.execute(
                "INSERT INTO events(created_at, category, level, message, camera_id, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (utc_now(), category, level, message, camera_id, json.dumps(payload or {})),
            )
            event_id = int(cursor.lastrowid)
        logger.log(getattr(logging, level.upper(), logging.INFO), "%s: %s", category, message)
        return event_id

    def list_events(
        self,
        limit: int = 100,
        category: str | None = None,
        camera_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM events", []
        filters = []
        if category:
            filters.append("category = ?")
            params.append(category)
        if camera_id:
            filters.append("camera_id = ?")
            params.append(camera_id)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self._lock, self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def record_occupancy_sample(
        self,
        camera_id: str,
        occupancy: int,
        tracking_count: int,
        fps: float,
        density: str,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "INSERT INTO occupancy_samples(created_at, camera_id, occupancy, tracking_count, fps, density) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (created_at or utc_now(), camera_id, occupancy, tracking_count, fps, density),
            )
            self._sample_writes += 1
            if self._sample_writes % 100 == 0:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=Config.ANALYTICS_RETENTION_DAYS)).isoformat(timespec="seconds")
                connection.execute("DELETE FROM occupancy_samples WHERE created_at < ?", (cutoff,))

    def analytics_history(
        self,
        camera_id: str | None,
        start_at: str,
        end_at: str,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT created_at, camera_id, occupancy, tracking_count, fps, density "
            "FROM occupancy_samples WHERE created_at >= ? AND created_at <= ?"
        )
        params: list[Any] = [start_at, end_at]
        if camera_id:
            query += " AND camera_id = ?"
            params.append(camera_id)
        query += " ORDER BY created_at ASC"
        with self._lock, self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def prune_analytics(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=Config.ANALYTICS_RETENTION_DAYS)).isoformat(timespec="seconds")
        with self._lock, self.connection() as connection:
            connection.execute("DELETE FROM occupancy_samples WHERE created_at < ?", (cutoff,))

    def count_events(self, category: str | None = None, level: str | None = None) -> int:
        filters, params = [], []
        if category:
            filters.append("category = ?")
            params.append(category)
        if level:
            filters.append("level = ?")
            params.append(level)
        query = "SELECT COUNT(*) FROM events" + (" WHERE " + " AND ".join(filters) if filters else "")
        with self._lock, self.connection() as connection:
            return int(connection.execute(query, params).fetchone()[0])

    def add_camera(self, camera: dict[str, Any]) -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO cameras(id, name, source, source_type, created_at, active) VALUES (?, ?, ?, ?, ?, ?)",
                (camera["id"], camera["name"], str(camera["source"]), camera["source_type"], camera["created_at"], int(camera.get("active", False))),
            )

    def set_camera_active(self, camera_id: str, active: bool) -> None:
        with self._lock, self.connection() as connection:
            connection.execute("UPDATE cameras SET active = ? WHERE id = ?", (int(active), camera_id))

    def delete_camera(self, camera_id: str) -> bool:
        with self._lock, self.connection() as connection:
            return connection.execute("DELETE FROM cameras WHERE id = ?", (camera_id,)).rowcount > 0

    def list_cameras(self) -> list[dict[str, Any]]:
        with self._lock, self.connection() as connection:
            rows = connection.execute("SELECT * FROM cameras ORDER BY created_at DESC").fetchall()
        return [{**dict(row), "active": bool(row["active"])} for row in rows]

    def add_report(self, report: dict[str, Any]) -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "INSERT INTO reports(id, created_at, format, filename, summary) VALUES (?, ?, ?, ?, ?)",
                (report["id"], report["created_at"], report["format"], report["filename"], json.dumps(report["summary"])),
            )

    def list_reports(self) -> list[dict[str, Any]]:
        with self._lock, self.connection() as connection:
            rows = connection.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
        return [{**dict(row), "summary": json.loads(row["summary"])} for row in rows]


_stores: dict[str, DataStore] = {}
_store_lock = threading.Lock()


def get_store(session_id: str | None = None) -> DataStore:
    from backend.session_manager import current_session_id, session_path
    identifier = session_id or current_session_id()
    with _store_lock:
        if identifier not in _stores:
            path = session_path(identifier, "data") / "smart_crowd.db" if identifier != "system" else Config.DATABASE_PATH
            _stores[identifier] = DataStore(path)
        return _stores[identifier]
