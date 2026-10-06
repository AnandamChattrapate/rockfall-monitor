"""SQLite event log."""
from __future__ import annotations

import os
import sqlite3
import threading


class EventStore:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts REAL, type TEXT, level TEXT, risk REAL, region TEXT, message TEXT)")
            self._db.commit()

    def add(self, ev: dict) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (ts, type, level, risk, region, message) VALUES (?,?,?,?,?,?)",
                (ev["ts"], ev["type"], ev["level"], ev["risk"], ev.get("region"), ev.get("message")))
            self._db.commit()
            return int(cur.lastrowid)

    def list(self, limit: int = 100) -> list:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, ts, type, level, risk, region, message FROM events"
                " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        keys = ("id", "ts", "type", "level", "risk", "region", "message")
        return [dict(zip(keys, r)) for r in rows]
