"""
Tests for the plugin system:
  - plugins/loader.py  (PluginLoader discovery, /help, /reload, unknown commands)
  - plugins/orch_plugin.py  (OrchPlugin)
  - plugins/write_plugin.py  (WritePlugin — path safety, pipe separator)
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from plugins.base import BasePlugin, PluginContext
from plugins.loader import PluginLoader
from plugins.orch_plugin import OrchPlugin
from plugins.write_plugin import WritePlugin, _safe_path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_plugin(trigger: str, name: str, description: str = "desc", usage: str = "use") -> type:
    """Dynamically build a minimal BasePlugin subclass for testing."""

    class _P(BasePlugin):
        pass

    _P.name = name
    _P.trigger = trigger
    _P.description = description
    _P.usage = usage
    _P.direct_result = True
    _P.run = lambda self, args, ctx: f"result of {trigger}"
    return _P


# ── PluginLoader — discovery ───────────────────────────────────────────────────

class TestPluginLoaderDiscovery:
    def test_discovers_plugins_from_plugins_dir(self):
        """PluginLoader.reload() must find at least the plugins shipped with the app."""
        loader = PluginLoader()
        # The repo ships at least these plugins
        expected_triggers = {"/git", "/note", "/search", "/read", "/write", "/open",
                             "/orch", "/telegram", "/session", "/test"}
        loaded = set(loader.plugins.keys())
        assert expected_triggers.issubset(loaded), (
            f"Missing triggers: {expected_triggers - loaded}"
        )

    def test_no_load_errors_for_shipped_plugins(self):
        """All bundled plugins must load without errors."""
        loader = PluginLoader()
        assert loader.load_errors == {}, (
            f"Plugin load errors: {loader.load_errors}"
        )

    def test_each_plugin_is_basePlugin_instance(self):
        """Every discovered plugin must be a BasePlugin instance."""
        loader = PluginLoader()
        for trigger, plugin in loader.plugins.items():
            assert isinstance(plugin, BasePlugin), (
                f"Plugin for '{trigger}' is not a BasePlugin instance"
            )

    def test_plugins_have_required_attributes(self):
        """Every plugin must expose name, trigger, description, usage."""
        loader = PluginLoader()
        for plugin in loader.plugins.values():
            assert plugin.name, f"Plugin {type(plugin).__name__} has empty name"
            assert plugin.trigger.startswith("/"), (
                f"Plugin {plugin.name} trigger must start with '/'"
            )
            assert plugin.description, f"Plugin {plugin.name} has empty description"


# ── PluginLoader — /help ───────────────────────────────────────────────────────

class TestPluginLoaderHelp:
    def test_help_returns_markdown_table(self):
        """/help must return a string containing a markdown table header."""
        loader = PluginLoader()
        ctx = PluginContext()
        result, is_direct = loader.execute("/help", ctx)

        assert is_direct is True
        assert "| Command |" in result
        assert "| Description |" in result
        assert "| Usage |" in result

    def test_help_lists_builtin_commands(self):
        """/help must include /help and /reload entries."""
        loader = PluginLoader()
        result, _ = loader.execute("/help", PluginContext())
        assert "`/help`" in result
        assert "`/reload`" in result

    def test_help_lists_all_loaded_plugins(self):
        """/help must include all loaded plugin triggers."""
        loader = PluginLoader()
        result, _ = loader.execute("/help", PluginContext())
        for trigger in loader.plugins:
            assert trigger in result, f"Trigger '{trigger}' missing from /help output"


# ── PluginLoader — /reload ─────────────────────────────────────────────────────

class TestPluginLoaderReload:
    def test_reload_rediscovers_plugins(self):
        """/reload must re-run discovery and return confirmation string."""
        loader = PluginLoader()
        initial_count = len(loader.plugins)

        result, is_direct = loader.execute("/reload", PluginContext())

        assert is_direct is True
        assert "reloaded" in result.lower()
        # Plugin count should be stable (nothing added/removed between reloads)
        assert len(loader.plugins) == initial_count

    def test_reload_clears_stale_plugins(self):
        """/reload must clear and re-populate the plugins dict."""
        loader = PluginLoader()
        # Manually inject a fake stale plugin
        loader.plugins["/fake_stale"] = MagicMock()

        loader.reload()

        assert "/fake_stale" not in loader.plugins

    def test_reload_returns_loaded_triggers_list(self):
        """/reload result string must include the list of loaded triggers."""
        loader = PluginLoader()
        result, _ = loader.execute("/reload", PluginContext())
        # Result contains the keys list representation
        assert "/git" in result or "git" in result  # at least one known trigger


# ── PluginLoader — unknown command ─────────────────────────────────────────────

class TestPluginLoaderUnknownCommand:
    def test_unknown_command_returns_error(self):
        """Unrecognised command must return an error message."""
        loader = PluginLoader()
        result, is_direct = loader.execute("/totally_unknown_xyz", PluginContext())

        assert is_direct is True
        assert "unknown command" in result.lower() or "Unknown command" in result

    def test_unknown_command_includes_available_commands(self):
        """Error message for unknown command must list available commands."""
        loader = PluginLoader()
        result, _ = loader.execute("/nosuchcmd", PluginContext())
        # Should mention at least /help
        assert "/help" in result

    def test_unknown_command_shows_the_bad_trigger(self):
        """Error message should echo back the command that was not found."""
        loader = PluginLoader()
        result, _ = loader.execute("/badcommand", PluginContext())
        assert "/badcommand" in result or "badcommand" in result


# ── OrchPlugin ────────────────────────────────────────────────────────────────

class TestOrchPlugin:
    def test_returns_error_when_no_orchestrator_in_context(self):
        """OrchPlugin must report 'not available' when ctx.extra has no orchestrator."""
        plugin = OrchPlugin()
        ctx = PluginContext(extra={})  # no orchestrator key

        result = plugin.run("list", ctx)

        assert "not available" in result.lower()

    def test_list_calls_tasks_summary(self, plugin_context: PluginContext):
        """'/orch list' must call orchestrator.tasks_summary()."""
        plugin = OrchPlugin()
        result = plugin.run("list", plugin_context)

        plugin_context.extra["orchestrator"].tasks_summary.assert_called_once()
        assert "Morning Brief" in result or "Orchestrator Tasks" in result

    def test_run_calls_run_now(self, plugin_context: PluginContext):
        """'/orch run <id>' must call orchestrator.run_now() with the correct id."""
        plugin = OrchPlugin()
        plugin.run("run morning_brief", plugin_context)

        plugin_context.extra["orchestrator"].run_now.assert_called_once_with("morning_brief")

    def test_run_without_id_returns_usage(self, plugin_context: PluginContext):
        """'/orch run' without an id must return a usage hint."""
        plugin = OrchPlugin()
        result = plugin.run("run", plugin_context)
        assert "usage" in result.lower() or "Usage" in result

    def test_logs_calls_format_runs_log(self, plugin_context: PluginContext):
        """'/orch logs' must call orchestrator.format_runs_log()."""
        plugin = OrchPlugin()
        plugin.run("logs", plugin_context)

        plugin_context.extra["orchestrator"].format_runs_log.assert_called()

    def test_unknown_subcommand_returns_error(self, plugin_context: PluginContext):
        """An unknown subcommand must return an error with usage hint."""
        plugin = OrchPlugin()
        result = plugin.run("frobnicate", plugin_context)
        assert "unknown" in result.lower() or "Unknown" in result

    def test_direct_result_is_true(self):
        """/orch plugin must have direct_result=True (output goes straight to chat)."""
        assert OrchPlugin.direct_result is True


# ── WritePlugin ───────────────────────────────────────────────────────────────

class TestWritePlugin:
    def test_requires_pipe_separator(self):
        """'/write' without '|' must return a usage error."""
        plugin = WritePlugin()
        ctx = PluginContext()
        result = plugin.run("some/path/without_pipe_separator", ctx)

        assert "Usage" in result or "usage" in result.lower()
        assert "|" in result  # usage example should contain pipe

    def test_rejects_path_traversal(self, tmp_path: Path):
        """_safe_path must return None for paths that escape CWD."""
        # Simulate CWD inside tmp_path so we control the boundary
        with patch("plugins.write_plugin.Path.cwd", return_value=tmp_path):
            safe = _safe_path("../../etc/passwd")
        assert safe is None

    def test_rejects_absolute_escape_path(self, tmp_path: Path):
        """_safe_path must reject absolute paths outside CWD."""
        with patch("plugins.write_plugin.Path.cwd", return_value=tmp_path):
            safe = _safe_path("/etc/passwd")
        assert safe is None

    def test_accepts_valid_relative_path(self, tmp_path: Path):
        """_safe_path must accept a path that stays inside CWD."""
        with patch("plugins.write_plugin.Path.cwd", return_value=tmp_path):
            safe = _safe_path("subdir/output.txt")
        assert safe is not None
        assert str(tmp_path) in str(safe)

    def test_write_creates_file(self, tmp_path: Path):
        """WritePlugin.run() must create the file with the given content."""
        plugin = WritePlugin()
        ctx = PluginContext()
        target = tmp_path / "output.txt"

        with patch("plugins.write_plugin.Path.cwd", return_value=tmp_path):
            result = plugin.run(f"output.txt | Hello, world!", ctx)

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "Hello, world!"
        assert "Written to" in result

    def test_write_reports_unsafe_path(self, tmp_path: Path):
        """WritePlugin.run() must refuse path traversal and include 'Unsafe path' in message."""
        plugin = WritePlugin()
        ctx = PluginContext()

        with patch("plugins.write_plugin.Path.cwd", return_value=tmp_path):
            result = plugin.run("../../etc/passwd | evil content", ctx)

        assert "Unsafe" in result or "unsafe" in result.lower()

    def test_append_mode_adds_content(self, tmp_path: Path):
        """WritePlugin in --append mode must add content to existing file."""
        plugin = WritePlugin()
        ctx = PluginContext()
        target = tmp_path / "log.txt"
        target.write_text("Line 1", encoding="utf-8")

        with patch("plugins.write_plugin.Path.cwd", return_value=tmp_path):
            result = plugin.run("--append log.txt | Line 2", ctx)

        content = target.read_text(encoding="utf-8")
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Appended" in result
