# Persistent OAuth/session storage (SQLite). Survives server restarts.

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent / "session_store.sqlite3"
_initialized = False


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    global _initialized
    if _initialized:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    _initialized = True


def load_session(session_id: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])
    finally:
        conn.close()


def save_session(session_id: str, data: dict[str, Any]) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO sessions (id, payload, updated_at)
            VALUES (?, ?, ?)
            """,
            (session_id, json.dumps(data, default=str), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()
