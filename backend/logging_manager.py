"""Public logging manager facade."""

from backend.data_store import get_store


class LoggingManager:
    """Writes and retrieves application events persisted in SQLite."""

    def log(self, category: str, level: str, message: str, camera_id: str | None = None, payload: dict | None = None) -> int:
        return get_store().log_event(category, level, message, camera_id, payload)

    def recent(self, limit: int = 100, category: str | None = None) -> list[dict]:
        return get_store().list_events(limit, category)
