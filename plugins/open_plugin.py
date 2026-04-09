"""
Open plugin — open a URL in the browser or a file/folder with the system default app.

Usage:
  /open https://example.com        → browser
  /open path/to/file.py            → default app (editor, viewer, etc.)
  /open logs/task_results/          → open folder in file manager
"""

from __future__ import annotations

import os
import platform
import subprocess
import webbrowser
from pathlib import Path

from plugins.base import BasePlugin, PluginContext


def _open_path(target: str) -> str:
    """Open a local file or folder with the OS default app."""
    p = Path(target)
    if not p.exists():
        # Try relative to CWD
        p = Path.cwd() / target
    if not p.exists():
        return f"Path not found: `{target}`"

    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(p.resolve()))
        elif system == "Darwin":
            subprocess.Popen(["open", str(p.resolve())])
        else:
            subprocess.Popen(["xdg-open", str(p.resolve())])
        kind = "folder" if p.is_dir() else "file"
        return f"Opened {kind}: `{p.resolve()}`"
    except Exception as e:
        return f"Could not open `{target}`: {e}"


class OpenPlugin(BasePlugin):
    name = "open"
    trigger = "/open"
    description = "Open a URL in browser, or a file/folder with the default OS app"
    usage = "/open <url | file-path | folder-path>"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        target = args.strip()
        if not target:
            return (
                "Usage: `/open <url | path>`\n\n"
                "Examples:\n"
                "- `/open https://github.com`\n"
                "- `/open logs/task_results/`\n"
                "- `/open agents/tasks/nba_telegram.py`"
            )

        if target.startswith("http://") or target.startswith("https://"):
            try:
                webbrowser.open(target)
                return f"Opened in browser: {target}"
            except Exception as e:
                return f"Could not open browser: {e}"

        return _open_path(target)
