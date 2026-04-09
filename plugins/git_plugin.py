"""Git plugin — read-only git operations in chat."""

from __future__ import annotations

import subprocess

from plugins.base import BasePlugin, PluginContext

# Only allow read-only commands by default
_READ_CMDS = {
    "status", "diff", "log", "branch", "remote",
    "stash", "tag", "show", "shortlog", "describe",
}


class GitPlugin(BasePlugin):
    name = "git"
    trigger = "/git"
    description = "Run git commands (read-only: status, diff, log, branch…)"
    usage = "/git [command] — e.g. /git status, /git log --oneline -10"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        args = args.strip() or "status"
        cmd_parts = args.split()
        git_dir = ctx.extra.get("git_dir", ".")

        if cmd_parts[0] not in _READ_CMDS:
            return (
                f"Command `git {cmd_parts[0]}` not allowed (read-only mode).\n"
                f"Allowed: {', '.join(sorted(_READ_CMDS))}"
            )

        try:
            result = subprocess.run(
                ["git"] + cmd_parts,
                cwd=git_dir,
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            output = (result.stdout or result.stderr or "(no output)").strip()
            return f"```\n$ git {args}\n\n{output}\n```"

        except FileNotFoundError:
            return "git not found — make sure git is installed and in PATH."
        except subprocess.TimeoutExpired:
            return "git command timed out (>15 s)."
        except Exception as e:
            return f"git error: {e}"
