"""Note plugin — save text directly to project memory from chat."""

from __future__ import annotations

from datetime import datetime

import memory_manager
from plugins.base import BasePlugin, PluginContext


class NotePlugin(BasePlugin):
    name = "note"
    trigger = "/note"
    description = "Save a note to the current project memory"
    usage = "/note [title | content]  or  /note content"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        if not args.strip():
            return (
                "Usage:\n"
                "- `/note My title | Note content here`\n"
                "- `/note Quick note without explicit title`"
            )

        if "|" in args:
            title, content = args.split("|", 1)
            title = title.strip()
            content = content.strip()
        else:
            title = f"Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            content = args.strip()

        path = memory_manager.save_note(ctx.project, title, content)
        return (
            f"Note saved to project **`{ctx.project}`**\n\n"
            f"**Title:** {title}\n"
            f"**File:** `{path}`"
        )
