"""
Tests for orchestrator.py — Orchestrator class.

APScheduler is mocked to avoid actually starting background threads.
SQLite DB is created in a tmp_path-isolated location per test.
schedule.json is written to tmp_path so tests are fully isolated.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We patch heavy dependencies before importing orchestrator so the module-level
# BackgroundScheduler instantiation is intercepted.
import orchestrator as orch_module
from orchestrator import Orchestrator


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Redirect SCHEDULE_FILE and DB_PATH to tmp_path so every test gets a clean slate.
    Also patches APScheduler so no real background threads are started.
    """
    schedule_file = tmp_path / "schedule.json"
    db_path = tmp_path / "logs" / "app.db"

    monkeypatch.setattr(orch_module, "SCHEDULE_FILE", schedule_file)
    monkeypatch.setattr(orch_module, "DB_PATH", db_path)

    # Patch the BackgroundScheduler class so no real threads start
    mock_scheduler_cls = MagicMock()
    mock_scheduler_instance = MagicMock()
    mock_scheduler_cls.return_value = mock_scheduler_instance
    monkeypatch.setattr(orch_module, "BackgroundScheduler", mock_scheduler_cls)

    yield

    # Cleanup is automatic via tmp_path


@pytest.fixture
def orch(tmp_path: Path) -> Orchestrator:
    """Return a fresh Orchestrator with empty schedule.json."""
    # Start with empty schedule to avoid DEFAULT_SCHEDULE noise in tests
    schedule_file = orch_module.SCHEDULE_FILE
    schedule_file.write_text("[]", encoding="utf-8")
    return Orchestrator()


def _sample_task(task_id: str = "my_task", schedule_type: str = "cron") -> dict:
    base = {
        "id": task_id,
        "name": "Test Task",
        "description": "For testing",
        "module": "agents.tasks.test_module",
        "schedule": schedule_type,
        "enabled": False,
        "last_run": None,
    }
    if schedule_type == "cron":
        base.update({"hour": 8, "minute": 30})
    else:
        base.update({"interval_minutes": 60})
    return base


# ── add_task ──────────────────────────────────────────────────────────────────

class TestAddTask:
    def test_add_task_appends_to_schedule(self, orch: Orchestrator):
        """add_task must persist the task to schedule.json."""
        task = _sample_task("new_task")
        orch.add_task(task)

        stored = orch.get_schedule()
        assert any(t["id"] == "new_task" for t in stored)

    def test_add_task_stores_all_fields(self, orch: Orchestrator):
        """add_task must store every field that was passed in."""
        task = _sample_task("full_task")
        orch.add_task(task)

        stored = next(t for t in orch.get_schedule() if t["id"] == "full_task")
        assert stored["name"] == task["name"]
        assert stored["module"] == task["module"]
        assert stored["schedule"] == task["schedule"]

    def test_add_task_raises_on_duplicate_id(self, orch: Orchestrator):
        """add_task must raise ValueError when a task with the same ID already exists."""
        task = _sample_task("dup_task")
        orch.add_task(task)

        with pytest.raises(ValueError, match="dup_task"):
            orch.add_task(task)

    def test_add_task_interval_type(self, orch: Orchestrator):
        """add_task must work for interval-type tasks."""
        task = _sample_task("interval_task", schedule_type="interval")
        orch.add_task(task)

        stored = next(t for t in orch.get_schedule() if t["id"] == "interval_task")
        assert stored["interval_minutes"] == 60

    def test_multiple_different_tasks_can_coexist(self, orch: Orchestrator):
        """Multiple tasks with distinct IDs must all persist."""
        for i in range(3):
            orch.add_task(_sample_task(f"task_{i}"))

        stored_ids = {t["id"] for t in orch.get_schedule()}
        assert {"task_0", "task_1", "task_2"} == stored_ids


# ── delete_task ───────────────────────────────────────────────────────────────

class TestDeleteTask:
    def test_delete_task_removes_from_schedule(self, orch: Orchestrator):
        """delete_task must remove the task from schedule.json."""
        orch.add_task(_sample_task("to_delete"))
        orch.delete_task("to_delete")

        stored = orch.get_schedule()
        assert not any(t["id"] == "to_delete" for t in stored)

    def test_delete_nonexistent_task_is_silent(self, orch: Orchestrator):
        """Deleting a task that does not exist must not raise."""
        orch.delete_task("ghost_task")  # should not raise

    def test_delete_leaves_other_tasks_intact(self, orch: Orchestrator):
        """delete_task must not affect other tasks in the schedule."""
        orch.add_task(_sample_task("keep_me"))
        orch.add_task(_sample_task("delete_me"))
        orch.delete_task("delete_me")

        stored_ids = {t["id"] for t in orch.get_schedule()}
        assert "keep_me" in stored_ids
        assert "delete_me" not in stored_ids


# ── update_task ───────────────────────────────────────────────────────────────

class TestUpdateTask:
    def test_update_task_changes_fields(self, orch: Orchestrator):
        """update_task must overwrite the matching task entry."""
        orch.add_task(_sample_task("updatable"))

        updated = _sample_task("updatable")
        updated["name"] = "Renamed Task"
        updated["hour"] = 12
        orch.update_task(updated)

        stored = next(t for t in orch.get_schedule() if t["id"] == "updatable")
        assert stored["name"] == "Renamed Task"
        assert stored["hour"] == 12

    def test_update_task_preserves_id(self, orch: Orchestrator):
        """update_task must not change the task ID."""
        orch.add_task(_sample_task("stable_id"))
        updated = _sample_task("stable_id")
        updated["name"] = "Different name"
        orch.update_task(updated)

        stored = orch.get_schedule()
        assert any(t["id"] == "stable_id" for t in stored)

    def test_update_nonexistent_task_does_not_add_new(self, orch: Orchestrator):
        """update_task on a missing ID must not add a new task entry."""
        orch.update_task(_sample_task("ghost"))

        stored_ids = {t["id"] for t in orch.get_schedule()}
        assert "ghost" not in stored_ids


# ── _execute_task ─────────────────────────────────────────────────────────────

class TestExecuteTask:
    def test_returns_error_for_missing_task(self, orch: Orchestrator):
        """_execute_task must return an error string if the task ID is not found."""
        result = orch._execute_task("nonexistent_id")
        assert "not found" in result.lower() or "nonexistent_id" in result

    def test_returns_error_for_invalid_module_path(self, orch: Orchestrator):
        """_execute_task must handle an invalid module path without crashing."""
        task = _sample_task("bad_module_task")
        task["module"] = "this has spaces"  # fails the module regex
        orch.add_task(task)

        result = orch._execute_task("bad_module_task")
        assert result  # something returned (error string)

    def test_returns_error_for_unimportable_module(self, orch: Orchestrator):
        """_execute_task must catch ImportError and return an error string."""
        task = _sample_task("missing_module_task")
        task["module"] = "agents.tasks.this_module_does_not_exist_xyz"
        orch.add_task(task)

        result = orch._execute_task("missing_module_task")
        # Should not raise — should return error string
        assert result  # non-empty error

    def test_executes_and_logs_to_db(self, orch: Orchestrator, tmp_path: Path):
        """_execute_task must insert a row into task_runs DB."""
        # Create a minimal fake module with a run() function
        fake_mod = MagicMock()
        fake_mod.run.return_value = "task done"
        task = _sample_task("logged_task")
        orch.add_task(task)

        with patch("importlib.import_module", return_value=fake_mod):
            result = orch._execute_task("logged_task")

        # Verify DB row was written
        with sqlite3.connect(orch_module.DB_PATH) as conn:
            row = conn.execute(
                "SELECT status, result FROM task_runs WHERE task_id='logged_task'"
            ).fetchone()

        assert row is not None
        assert row[0] == "success"
        assert "task done" in row[1]

    def test_execute_records_error_status_on_exception(self, orch: Orchestrator):
        """_execute_task must set status='error' in DB when the module raises."""
        exploding_mod = MagicMock()
        exploding_mod.run.side_effect = RuntimeError("boom")
        task = _sample_task("exploding_task")
        orch.add_task(task)

        with patch("importlib.import_module", return_value=exploding_mod):
            orch._execute_task("exploding_task")

        with sqlite3.connect(orch_module.DB_PATH) as conn:
            row = conn.execute(
                "SELECT status, error FROM task_runs WHERE task_id='exploding_task'"
            ).fetchone()

        assert row is not None
        assert row[0] == "error"
        assert "boom" in row[1]


# ── format_runs_log ───────────────────────────────────────────────────────────

class TestFormatRunsLog:
    def test_returns_no_runs_message_when_empty(self, orch: Orchestrator):
        """format_runs_log must return a human-readable 'no runs' message when DB is empty."""
        result = orch.format_runs_log()
        assert result  # non-empty
        assert "no" in result.lower() or "yet" in result.lower()

    def test_returns_markdown_string_with_runs(self, orch: Orchestrator):
        """format_runs_log must return a markdown table when runs exist."""
        # Insert a fake run directly into the DB
        with sqlite3.connect(orch_module.DB_PATH) as conn:
            conn.execute(
                """INSERT INTO task_runs
                   (id, task_id, task_name, started_at, finished_at, status, result, error)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("abc123", "my_task", "My Task",
                 "2026-04-09T06:00:00", "2026-04-09T06:00:03",
                 "success", "done", ""),
            )

        result = orch.format_runs_log()

        assert "|" in result  # markdown table
        assert "My Task" in result
        assert "success" in result

    def test_filters_by_task_id(self, orch: Orchestrator):
        """format_runs_log(task_id) must return only rows for that task."""
        with sqlite3.connect(orch_module.DB_PATH) as conn:
            conn.executemany(
                """INSERT INTO task_runs
                   (id, task_id, task_name, started_at, finished_at, status, result, error)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [
                    ("r1", "task_a", "Task A", "2026-04-09T06:00:00", "2026-04-09T06:00:01", "success", "ok", ""),
                    ("r2", "task_b", "Task B", "2026-04-09T07:00:00", "2026-04-09T07:00:02", "error", "", "fail"),
                ],
            )

        result = orch.format_runs_log(task_id="task_a")

        assert "Task A" in result
        assert "Task B" not in result

    def test_result_is_string(self, orch: Orchestrator):
        """format_runs_log must always return a string, never None."""
        result = orch.format_runs_log()
        assert isinstance(result, str)

    def test_result_includes_status_icons(self, orch: Orchestrator):
        """format_runs_log must include status icons for success and error runs."""
        with sqlite3.connect(orch_module.DB_PATH) as conn:
            conn.executemany(
                """INSERT INTO task_runs
                   (id, task_id, task_name, started_at, finished_at, status, result, error)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [
                    ("s1", "t1", "T1", "2026-04-09T06:00:00", "2026-04-09T06:00:01", "success", "ok", ""),
                    ("s2", "t2", "T2", "2026-04-09T07:00:00", "2026-04-09T07:00:02", "error", "", "fail"),
                ],
            )

        result = orch.format_runs_log()
        assert "✅" in result
        assert "❌" in result
