"""
SQLite-based conversation session management.

Every chat conversation is saved as a session with:
  - unique ID, project, preset, model
  - full message history (JSON)
  - timestamps (created_at, updated_at)

DB location: logs/app.db
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path("logs/app.db")


# ── DB init ────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                project     TEXT NOT NULL DEFAULT 'default',
                title       TEXT NOT NULL DEFAULT 'Untitled',
                preset      TEXT NOT NULL DEFAULT 'General',
                model       TEXT NOT NULL DEFAULT 'gemma4:e2b',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                messages    TEXT NOT NULL DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_project
            ON sessions(project, updated_at DESC)
        """)
        conn.commit()


# ── Public API ─────────────────────────────────────────────────────────────────

def new_id() -> str:
    """Generate a short unique session ID."""
    return uuid.uuid4().hex[:10]


def save_session(
    session_id: str,
    project: str,
    title: str,
    preset: str,
    model: str,
    messages: list[dict],
) -> None:
    """Insert or update a session. Preserves original created_at on update."""
    _init_db()
    now = datetime.now().isoformat(timespec="seconds")
    messages_json = json.dumps(messages, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT created_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        created_at = existing[0] if existing else now
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, project, title, preset, model, created_at, updated_at, messages)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, project, title[:120], preset, model, created_at, now, messages_json),
        )


def list_sessions(project: str | None = None, limit: int = 200) -> list[dict]:
    """Return sessions ordered by most recently updated."""
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        if project and project != "__all__":
            rows = conn.execute(
                """SELECT id, project, title, preset, model, created_at, updated_at
                   FROM sessions WHERE project = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (project, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, project, title, preset, model, created_at, updated_at
                   FROM sessions ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    cols = ["id", "project", "title", "preset", "model", "created_at", "updated_at"]
    return [dict(zip(cols, r)) for r in rows]


def load_session(session_id: str) -> dict | None:
    """Load full session including messages. Returns None if not found."""
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not row:
        return None
    cols = ["id", "project", "title", "preset", "model", "created_at", "updated_at", "messages"]
    data = dict(zip(cols, row))
    data["messages"] = json.loads(data["messages"])
    return data


def delete_session(session_id: str) -> None:
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def format_label(s: dict) -> str:
    """Format session dict as a human-readable dropdown label."""
    dt = s["updated_at"][:16].replace("T", " ")
    title = s["title"]
    if len(title) > 38:
        title = title[:38] + "…"
    return f"{dt}  [{s['project']}]  {title}"


def session_choices(project: str | None = None) -> list[tuple[str, str]]:
    """Return list of (label, session_id) for gr.Dropdown choices."""
    sessions = list_sessions(project)
    return [(format_label(s), s["id"]) for s in sessions]


def search_sessions(query: str, project: str | None = None) -> list[dict]:
    """Simple keyword search in session titles and messages."""
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        if project and project != "__all__":
            rows = conn.execute(
                """SELECT id, project, title, preset, model, created_at, updated_at
                   FROM sessions
                   WHERE project = ? AND (title LIKE ? OR messages LIKE ?)
                   ORDER BY updated_at DESC LIMIT 50""",
                (project, f"%{query}%", f"%{query}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, project, title, preset, model, created_at, updated_at
                   FROM sessions
                   WHERE title LIKE ? OR messages LIKE ?
                   ORDER BY updated_at DESC LIMIT 50""",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
    cols = ["id", "project", "title", "preset", "model", "created_at", "updated_at"]
    return [dict(zip(cols, r)) for r in rows]
