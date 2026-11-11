"""In-memory ring buffer of backend events (provider errors, mock-fallback
notices, summary-refresh results) -- surfaced in the frontend's Logs tab.
Nothing here is persisted to disk; it resets on restart.
"""

from __future__ import annotations

import time
from collections import deque

_MAX_LOGS = 200
_LOGS: deque[dict] = deque(maxlen=_MAX_LOGS)
_seq = 0


def log(level: str, source: str, message: str) -> None:
    """Record one event. ``level`` is "info" | "warn" | "error"."""
    global _seq
    _seq += 1
    _LOGS.append({"id": _seq, "ts": time.time(), "level": level, "source": source, "message": message})


def get_logs(since_id: int = 0) -> list[dict]:
    """Entries with id > since_id, oldest first. ``since_id=0`` returns all
    currently retained entries (older ones fall off the ring buffer)."""
    return [e for e in _LOGS if e["id"] > since_id]


def clear() -> None:
    _LOGS.clear()
