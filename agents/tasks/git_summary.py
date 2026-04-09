"""
Git Summary task — runs git log/status and saves a summary.

Schedule: interval, every 120 minutes
Output: logs/task_results/git_summary_YYYY-MM-DD_HHMM.md
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def run(task: dict) -> str:
    git_dir = task.get("git_dir", ".")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    sections: list[str] = [f"# Git Summary — {ts}", ""]

    for cmd, label in [
        (["git", "status", "--short"], "Status"),
        (["git", "log", "--oneline", "-10"], "Last 10 commits"),
        (["git", "branch", "-v"], "Branches"),
    ]:
        try:
            result = subprocess.run(
                cmd,
                cwd=git_dir,
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            output = (result.stdout or result.stderr or "(empty)").strip()
            sections += [f"## {label}", f"```\n{output}\n```", ""]
        except FileNotFoundError:
            sections += [f"## {label}", "git not found in PATH.", ""]
        except Exception as e:
            sections += [f"## {label}", f"Error: {e}", ""]

    summary = "\n".join(sections)

    output_dir = Path("logs/task_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    fpath = output_dir / f"git_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    fpath.write_text(summary, encoding="utf-8")

    # Return short status for the log
    status_line = sections[3] if len(sections) > 3 else "completed"
    return f"Git summary saved to {fpath}\n{status_line[:200]}"
