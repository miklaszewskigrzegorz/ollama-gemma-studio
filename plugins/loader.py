"""
Plugin auto-discovery and execution.

Scans plugins/*_plugin.py for classes inheriting BasePlugin.
Reload at runtime via loader.reload().
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

from plugins.base import BasePlugin, PluginContext

_PLUGINS_DIR = Path("plugins")


class PluginLoader:
    def __init__(self) -> None:
        self.plugins: dict[str, BasePlugin] = {}
        self.load_errors: dict[str, str] = {}
        self.reload()

    # ── Discovery ──────────────────────────────────────────────────────────────

    def reload(self) -> None:
        """(Re-)discover all plugins in plugins/*_plugin.py."""
        self.plugins.clear()
        self.load_errors.clear()

        for py_file in sorted(_PLUGINS_DIR.glob("*_plugin.py")):
            module_name = f"plugins.{py_file.stem}"
            try:
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    module = importlib.import_module(module_name)

                for _, cls in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(cls, BasePlugin)
                        and cls is not BasePlugin
                        and cls.__module__ == module_name
                    ):
                        instance = cls()
                        self.plugins[instance.trigger] = instance

            except Exception as e:
                self.load_errors[py_file.name] = str(e)
                print(f"  [plugins] load error {py_file.name}: {e}")

    # ── Execution ──────────────────────────────────────────────────────────────

    def is_command(self, message: str) -> bool:
        return message.strip().startswith("/")

    def execute(self, message: str, ctx: PluginContext) -> tuple[str, bool]:
        """
        Parse and execute a plugin command.

        Returns:
            (result_str, is_direct)
            is_direct=True  → show result directly in chat (no LLM)
            is_direct=False → prepend result as LLM context
        """
        parts = message.strip().split(None, 1)
        trigger = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Built-in: /help
        if trigger == "/help":
            return self._help_text(), True

        # Built-in: /reload (hot-reload plugins)
        if trigger == "/reload":
            self.reload()
            return f"Plugins reloaded. Loaded: {list(self.plugins.keys())}", True

        plugin = self.plugins.get(trigger)
        if plugin is None:
            available = ", ".join(sorted(["/help", "/reload"] + list(self.plugins.keys())))
            return (
                f"Unknown command: `{trigger}`\n\n"
                f"Available commands: {available}",
                True,
            )

        try:
            result = plugin.run(args, ctx)
            return result, plugin.direct_result
        except Exception as e:
            return f"**Plugin error** (`{plugin.name}`): {e}", True

    # ── Help ───────────────────────────────────────────────────────────────────

    def _help_text(self) -> str:
        lines = [
            "## Available Commands\n",
            "| Command | Description | Usage |",
            "|---|---|---|",
            "| `/help` | Show this help | `/help` |",
            "| `/reload` | Hot-reload all plugins | `/reload` |",
        ]
        for p in sorted(self.plugins.values(), key=lambda x: x.trigger):
            desc = p.description.replace("|", "\\|")
            usage = p.usage.replace("|", "\\|")
            lines.append(f"| `{p.trigger}` | {desc} | `{usage}` |")

        if self.load_errors:
            lines += ["", "**Load errors:**"]
            for fname, err in self.load_errors.items():
                lines.append(f"- `{fname}`: {err}")

        return "\n".join(lines)

    def list_all(self) -> list[dict]:
        result = [
            {"trigger": "/help",   "name": "help",   "description": "Show help",           "usage": "/help"},
            {"trigger": "/reload", "name": "reload", "description": "Hot-reload plugins",  "usage": "/reload"},
        ]
        result += [
            {
                "trigger": p.trigger,
                "name": p.name,
                "description": p.description,
                "usage": p.usage,
                "direct": p.direct_result,
            }
            for p in sorted(self.plugins.values(), key=lambda x: x.trigger)
        ]
        return result
