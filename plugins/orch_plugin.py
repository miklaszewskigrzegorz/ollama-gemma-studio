"""
Orchestrator plugin — manage scheduled tasks from chat.

Commands:
  /orch list                          list all tasks
  /orch run <id>                      run task immediately
  /orch enable <id>                   enable task
  /orch disable <id>                  disable task
  /orch delete <id>                   delete task
  /orch add id=X name=Y module=Z schedule=cron hour=8 minute=50 [enabled=true]
  /orch add id=X name=Y module=Z schedule=interval interval=60 [enabled=true]
  /orch logs [id]                     show execution log
"""

from __future__ import annotations

import json
import re

from plugins.base import BasePlugin, PluginContext

_KV_RE = re.compile(r'(\w+)=(".*?"|\'.*?\'|\S+)')


def _parse_kv(args: str) -> dict[str, str]:
    """Parse key=value pairs from args string."""
    result = {}
    for k, v in _KV_RE.findall(args):
        result[k] = v.strip('"\'')
    return result


class OrchPlugin(BasePlugin):
    name = "orch"
    trigger = "/orch"
    description = "Manage Orchestrator tasks from chat (add, run, enable, list)"
    usage = "/orch list | run <id> | enable <id> | disable <id> | add id=X name=Y module=Z schedule=cron hour=8 minute=50"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        orch = ctx.extra.get("orchestrator")
        if orch is None:
            return "Orchestrator not available in this context."

        args = args.strip()
        parts = args.split(None, 1)
        cmd = parts[0].lower() if parts else "list"
        rest = parts[1] if len(parts) > 1 else ""

        if cmd == "list":
            return self._list(orch)
        if cmd == "run":
            return self._run(orch, rest.strip())
        if cmd == "enable":
            return self._set_enabled(orch, rest.strip(), True)
        if cmd == "disable":
            return self._set_enabled(orch, rest.strip(), False)
        if cmd == "delete":
            return self._delete(orch, rest.strip())
        if cmd == "add":
            return self._add(orch, rest.strip())
        if cmd in ("log", "logs"):
            tid = rest.strip() or None
            return orch.format_runs_log(tid) or "_No runs yet._"
        return (
            f"Unknown subcommand: `{cmd}`\n\n"
            "Usage: `/orch list | run <id> | enable <id> | disable <id> | delete <id> | add ... | logs [id]`"
        )

    # ── Subcommands ────────────────────────────────────────────────────────────

    def _list(self, orch) -> str:
        tasks = orch.tasks_summary()
        if not tasks:
            return "_No tasks configured._"
        lines = [
            "## Orchestrator Tasks\n",
            "| ID | Name | Schedule | Next Run | Last Status | Enabled |",
            "|---|---|---|---|---|---|",
        ]
        for t in tasks:
            sched = (
                f"cron {t.get('hour', 0):02d}:{t.get('minute', 0):02d}"
                if t.get("schedule") == "cron"
                else f"every {t.get('interval_minutes', 60)}m"
            )
            enabled = "yes" if t.get("enabled") else "no"
            lines.append(
                f"| `{t['id']}` | {t['name']} | {sched} "
                f"| {t.get('next_run', '?')} | {t.get('last_status', 'never')} | {enabled} |"
            )
        return "\n".join(lines)

    def _run(self, orch, task_id: str) -> str:
        if not task_id:
            return "Usage: `/orch run <task_id>`"
        result = orch.run_now(task_id)
        return f"**Run result for `{task_id}`:**\n\n```\n{result[:1000]}\n```"

    def _set_enabled(self, orch, task_id: str, enabled: bool) -> str:
        if not task_id:
            return f"Usage: `/orch {'enable' if enabled else 'disable'} <task_id>`"
        tasks = orch.get_schedule()
        if not any(t["id"] == task_id for t in tasks):
            ids = [t["id"] for t in tasks]
            return f"Task `{task_id}` not found. Available: {ids}"
        orch.set_enabled(task_id, enabled)
        state = "enabled" if enabled else "disabled"
        return f"Task `{task_id}` is now **{state}**."

    def _delete(self, orch, task_id: str) -> str:
        if not task_id:
            return "Usage: `/orch delete <task_id>`"
        orch.delete_task(task_id)
        return f"Task `{task_id}` deleted."

    def _add(self, orch, args: str) -> str:
        kv = _parse_kv(args)

        task_id = kv.get("id", "").strip().replace(" ", "_")
        name = kv.get("name", task_id)
        module = kv.get("module", "")
        schedule = kv.get("schedule", "cron")
        enabled = kv.get("enabled", "false").lower() in ("true", "1", "yes")

        if not task_id:
            return "Missing required field: `id=<task_id>`"
        if not module:
            return "Missing required field: `module=agents.tasks.<name>`"

        task: dict = {
            "id": task_id,
            "name": name,
            "description": kv.get("description", ""),
            "module": module,
            "schedule": schedule,
            "enabled": enabled,
            "last_run": None,
        }

        if schedule == "cron":
            task["hour"] = int(kv.get("hour", 6))
            task["minute"] = int(kv.get("minute", 0))
        else:
            task["interval_minutes"] = int(kv.get("interval", kv.get("interval_minutes", 60)))

        try:
            orch.add_task(task)
        except ValueError as e:
            return f"Error: {e}\n\nUse `/orch delete {task_id}` first if you want to replace it."

        sched_str = (
            f"cron at {task.get('hour', 0):02d}:{task.get('minute', 0):02d}"
            if schedule == "cron"
            else f"every {task.get('interval_minutes')} min"
        )
        status = "enabled" if enabled else "disabled (use `/orch enable {task_id}` to activate)"

        return (
            f"Task **`{task_id}`** added successfully.\n\n"
            f"- **Module:** `{module}`\n"
            f"- **Schedule:** {sched_str}\n"
            f"- **Status:** {status}\n\n"
            f"```json\n{json.dumps(task, indent=2)}\n```"
        )
