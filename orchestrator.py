"""
CRON Orchestrator — APScheduler-based task runner.

Task types:
  cron     → run at specific time daily (hour, minute)
  interval → run every N minutes

Schedule stored in: schedule.json
Run logs stored in: logs/app.db (table: task_runs)

Usage:
    from orchestrator import Orchestrator
    orch = Orchestrator()
    orch.start()   # starts BackgroundScheduler
    orch.stop()    # graceful shutdown
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger("orchestrator")

SCHEDULE_FILE = Path("schedule.json")
DB_PATH = Path("logs/app.db")

# Timezone from env (TZ=Europe/Warsaw) — falls back to UTC which is always safe
_TIMEZONE = os.getenv("TZ", "UTC")

# Module path must be dot-separated identifiers only (prevents arbitrary imports)
_MODULE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$")

# ── Default task definitions (installed once if schedule.json missing) ─────────

DEFAULT_SCHEDULE: list[dict] = [
    {
        "id": "morning_brief",
        "name": "Morning Brief",
        "description": "Daily AI productivity summary",
        "module": "agents.tasks.morning_brief",
        "schedule": "cron",
        "hour": 6,
        "minute": 0,
        "enabled": False,
        "model": "gemma4:e2b",
        "last_run": None,
    },
    {
        "id": "git_summary",
        "name": "Git Status Check",
        "description": "Periodic git status log",
        "module": "agents.tasks.git_summary",
        "schedule": "interval",
        "interval_minutes": 120,
        "enabled": False,
        "git_dir": ".",
        "last_run": None,
    },
]


# ── DB schema ──────────────────────────────────────────────────────────────────

def _ensure_schema() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_runs (
                id          TEXT PRIMARY KEY,
                task_id     TEXT NOT NULL,
                task_name   TEXT,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                status      TEXT NOT NULL DEFAULT 'running',
                result      TEXT,
                error       TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_runs_task
            ON task_runs(task_id, started_at DESC)
        """)
        conn.commit()


# ── Orchestrator ───────────────────────────────────────────────────────────────

class Orchestrator:

    def __init__(self) -> None:
        _ensure_schema()
        self._running = False
        self.scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone=_TIMEZONE,
        )
        # Ensure schedule.json exists
        if not SCHEDULE_FILE.exists():
            self._write_schedule(DEFAULT_SCHEDULE)
        self._load_all_jobs()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self._running:
            self.scheduler.start()
            self._running = True
            log.info("Orchestrator started")

    def stop(self) -> None:
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            log.info("Orchestrator stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Schedule file I/O ──────────────────────────────────────────────────────

    def get_schedule(self) -> list[dict]:
        if not SCHEDULE_FILE.exists():
            return []
        try:
            with open(SCHEDULE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_schedule(self, tasks: list[dict]) -> None:
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

    def _load_all_jobs(self) -> None:
        for task in self.get_schedule():
            if task.get("enabled", False):
                self._register_job(task)

    # ── Job management ─────────────────────────────────────────────────────────

    def _register_job(self, task: dict) -> None:
        task_id = task["id"]
        stype = task.get("schedule", "interval")

        def wrapper():
            self._execute_task(task_id)

        if stype == "cron":
            trigger = CronTrigger(
                hour=task.get("hour", 0),
                minute=task.get("minute", 0),
                timezone=_TIMEZONE,
            )
        elif stype == "interval":
            trigger = IntervalTrigger(
                minutes=int(task.get("interval_minutes", 60))
            )
        else:
            log.warning(f"Unknown schedule type '{stype}' for task {task_id}")
            return

        try:
            self.scheduler.add_job(
                wrapper,
                trigger=trigger,
                id=task_id,
                name=task.get("name", task_id),
                replace_existing=True,
            )
            log.info(f"Registered job: {task_id} ({stype})")
        except Exception as e:
            log.error(f"Failed to register job {task_id}: {e}")

    def _execute_task(self, task_id: str) -> str:
        """Run a task by ID, log to DB. Returns result string."""
        tasks = self.get_schedule()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return f"Task not found: {task_id}"

        run_id = uuid.uuid4().hex[:8]
        started = datetime.now().isoformat(timespec="seconds")
        log.info(f"Task start: {task['name']} ({run_id})")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO task_runs (id, task_id, task_name, started_at, status) VALUES (?,?,?,?,'running')",
                (run_id, task_id, task.get("name", task_id), started),
            )

        result = ""
        error = ""
        status = "success"
        try:
            module_path = task.get("module")
            if not module_path:
                result = f"Task {task['name']} triggered (no module configured)"
            elif not _MODULE_RE.match(module_path):
                raise ValueError(f"Invalid module path: {module_path!r}")
            else:
                mod = importlib.import_module(module_path)
                result = str(mod.run(task))

        except Exception as e:
            error = str(e)
            status = "error"
            log.error(f"Task {task_id} failed: {e}")

        finished = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE task_runs SET finished_at=?, status=?, result=?, error=? WHERE id=?",
                (finished, status, result[:4000], error[:1000], run_id),
            )

        # Update last_run field in schedule.json
        for t in tasks:
            if t["id"] == task_id:
                t["last_run"] = finished
                break
        self._write_schedule(tasks)

        log.info(f"Task end: {task['name']} — {status}")
        return result or error

    # ── Public task operations ─────────────────────────────────────────────────

    def run_now(self, task_id: str) -> str:
        """Execute a task immediately (blocking, returns result)."""
        return self._execute_task(task_id)

    def add_task(self, task: dict) -> None:
        tasks = self.get_schedule()
        if any(t["id"] == task["id"] for t in tasks):
            raise ValueError(f"Task ID already exists: {task['id']}")
        tasks.append(task)
        self._write_schedule(tasks)
        if task.get("enabled", False) and self._running:
            self._register_job(task)

    def update_task(self, task: dict) -> None:
        tasks = self.get_schedule()
        for i, t in enumerate(tasks):
            if t["id"] == task["id"]:
                tasks[i] = task
                break
        self._write_schedule(tasks)
        if self._running:
            if self.scheduler.get_job(task["id"]):
                self.scheduler.remove_job(task["id"])
            if task.get("enabled", False):
                self._register_job(task)

    def delete_task(self, task_id: str) -> None:
        tasks = [t for t in self.get_schedule() if t["id"] != task_id]
        self._write_schedule(tasks)
        if self._running and self.scheduler.get_job(task_id):
            self.scheduler.remove_job(task_id)

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        tasks = self.get_schedule()
        for t in tasks:
            if t["id"] == task_id:
                t["enabled"] = enabled
                break
        self._write_schedule(tasks)
        if self._running:
            job = self.scheduler.get_job(task_id)
            if enabled:
                task = next((t for t in tasks if t["id"] == task_id), None)
                if task:
                    self._register_job(task)
            elif job:
                self.scheduler.remove_job(task_id)

    # ── Status & logs ──────────────────────────────────────────────────────────

    def next_run(self, task_id: str) -> str:
        if not self._running:
            return "stopped"
        job = self.scheduler.get_job(task_id)
        if not job:
            return "not scheduled"
        if job.next_run_time is None:
            return "paused"
        return job.next_run_time.strftime("%Y-%m-%d %H:%M")

    def tasks_summary(self) -> list[dict]:
        """Return all tasks enriched with scheduler status and last run result."""
        tasks = self.get_schedule()
        result = []
        for t in tasks:
            runs = self.get_runs(t["id"], limit=1)
            last_status = runs[0]["status"] if runs else "never"
            icon = "🟢" if t.get("enabled") else "⚪"
            result.append({
                **t,
                "next_run": self.next_run(t["id"]),
                "last_status": last_status,
                "icon": icon,
            })
        return result

    def get_runs(self, task_id: str | None = None, limit: int = 50) -> list[dict]:
        with sqlite3.connect(DB_PATH) as conn:
            if task_id:
                rows = conn.execute(
                    """SELECT id, task_id, task_name, started_at, finished_at,
                              status, result, error
                       FROM task_runs WHERE task_id=?
                       ORDER BY started_at DESC LIMIT ?""",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, task_id, task_name, started_at, finished_at,
                              status, result, error
                       FROM task_runs ORDER BY started_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        cols = ["id", "task_id", "task_name", "started_at", "finished_at",
                "status", "result", "error"]
        return [dict(zip(cols, r)) for r in rows]

    def format_runs_log(self, task_id: str | None = None) -> str:
        """Format run history as a markdown table."""
        runs = self.get_runs(task_id, limit=30)
        if not runs:
            return "_No task runs yet._"
        lines = ["| Started | Task | Status | Duration | Result |",
                 "|---|---|---|---|---|"]
        for r in runs:
            start = r["started_at"][:16] if r["started_at"] else "?"
            name = r["task_name"] or r["task_id"]
            status_icon = {"success": "✅", "error": "❌", "running": "⏳"}.get(r["status"], "?")
            duration = ""
            if r["started_at"] and r["finished_at"]:
                try:
                    s = datetime.fromisoformat(r["started_at"])
                    f = datetime.fromisoformat(r["finished_at"])
                    duration = f"{int((f - s).total_seconds())}s"
                except Exception:
                    duration = "?"
            result_preview = (r["result"] or r["error"] or "")[:60].replace("\n", " ")
            lines.append(f"| {start} | {name} | {status_icon} {r['status']} | {duration} | {result_preview} |")
        return "\n".join(lines)
