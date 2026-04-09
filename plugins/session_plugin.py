"""Session plugin — show info about the current session."""

from __future__ import annotations

import session_manager
from plugins.base import BasePlugin, PluginContext


class SessionPlugin(BasePlugin):
    name = "session"
    trigger = "/session"
    description = "Show current session info or list recent sessions"
    usage = "/session  or  /session list"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        args = args.strip().lower()

        if args == "list":
            sessions = session_manager.list_sessions(
                project=ctx.project if ctx.project != "__all__" else None,
                limit=10,
            )
            if not sessions:
                return "No sessions found."
            lines = ["## Recent Sessions\n"]
            for s in sessions:
                lines.append(
                    f"- `{s['id']}` — {s['updated_at'][:16]} | "
                    f"**{s['project']}** | {s['preset']} | {s['title'][:40]}"
                )
            return "\n".join(lines)

        # Default: current session info from context
        session_id = ctx.extra.get("session_id", "unknown")
        return (
            f"## Current Session\n\n"
            f"- **ID:** `{session_id}`\n"
            f"- **Project:** {ctx.project}\n"
            f"- **Preset:** {ctx.preset}\n"
            f"- **Model:** {ctx.model}\n"
            f"- **Messages:** {len(ctx.history)}\n\n"
            f"Use `/session list` to see recent sessions."
        )
