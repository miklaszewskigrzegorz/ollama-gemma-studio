"""
Shared pytest fixtures for Local LLM Assistant test suite.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plugins.base import PluginContext


# ── Memory / filesystem fixtures ───────────────────────────────────────────────


@pytest.fixture
def tmp_memory_dir(tmp_path: Path) -> Path:
    """
    Temporary directory that mimics the structure of the memory/ folder.

    Creates a couple of stub .md files so tests that scan for memory files
    have something to discover.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()

    # Default project memory file
    (memory_dir / "default.md").write_text(
        "# Default project\n\nStub memory for tests.\n",
        encoding="utf-8",
    )
    # A second project
    (memory_dir / "my_project.md").write_text(
        "# My Project\n\nAnother stub.\n",
        encoding="utf-8",
    )
    return memory_dir


# ── Orchestrator mock ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """
    MagicMock that quacks like an Orchestrator instance.

    Pre-configured with sensible return values so plugin / unit tests do not
    need to set them up individually.
    """
    orch = MagicMock(name="Orchestrator")

    # get_schedule returns a minimal task list by default
    orch.get_schedule.return_value = [
        {
            "id": "morning_brief",
            "name": "Morning Brief",
            "module": "agents.tasks.morning_brief",
            "schedule": "cron",
            "hour": 6,
            "minute": 0,
            "enabled": False,
            "last_run": None,
        },
        {
            "id": "git_summary",
            "name": "Git Summary",
            "module": "agents.tasks.git_summary",
            "schedule": "interval",
            "interval_minutes": 120,
            "enabled": True,
            "last_run": "2026-04-09T06:00:00",
        },
    ]

    orch.tasks_summary.return_value = [
        {
            "id": "morning_brief",
            "name": "Morning Brief",
            "schedule": "cron",
            "hour": 6,
            "minute": 0,
            "enabled": False,
            "next_run": "not scheduled",
            "last_status": "never",
            "icon": "⚪",
        },
        {
            "id": "git_summary",
            "name": "Git Summary",
            "schedule": "interval",
            "interval_minutes": 120,
            "enabled": True,
            "next_run": "2026-04-09 08:00",
            "last_status": "success",
            "icon": "🟢",
        },
    ]

    orch.run_now.return_value = "Task executed successfully."
    orch.format_runs_log.return_value = (
        "| Started | Task | Status | Duration | Result |\n"
        "|---|---|---|---|---|\n"
        "| 2026-04-09 06:00 | Morning Brief | ✅ success | 3s | Done |"
    )
    orch.is_running = True

    return orch


# ── Plugin context fixture ─────────────────────────────────────────────────────


@pytest.fixture
def plugin_context(mock_orchestrator: MagicMock) -> PluginContext:
    """
    A PluginContext with default values suitable for most plugin tests.

    Includes the mock_orchestrator in ctx.extra so /orch plugin tests work
    without additional setup.
    """
    return PluginContext(
        project="test_project",
        preset="General",
        model="gemma4:e2b",
        history=[],
        extra={
            "orchestrator": mock_orchestrator,
            "git_dir": ".",
        },
    )
