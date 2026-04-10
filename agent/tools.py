"""
Agent tool definitions and implementations.

Two categories:
  AUTO tools  — execute immediately, return result string:
                read_file, list_directory, search_files, grep_code
  WRITE tools — buffered as PendingAction, require user confirmation:
                write_file, run_command

Tool schemas follow the Ollama function-calling format and are passed directly
to ollama.chat(tools=AGENT_TOOL_SCHEMAS).
"""
from __future__ import annotations

import dataclasses
import fnmatch
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.scope_guard import ScopeGuard, ScopeViolation

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_FILE_CHARS = 15_000     # truncate large files at this many characters
MAX_GREP_RESULTS = 60       # max matching lines returned by grep_code
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "env", ".tox"}

AUTO_TOOL_NAMES = frozenset({"read_file", "list_directory", "search_files", "grep_code"})
WRITE_TOOL_NAMES = frozenset({"write_file", "run_command"})

# ── PendingAction ─────────────────────────────────────────────────────────────


@dataclass
class PendingAction:
    """Write-class action buffered for user confirmation."""
    action_id: str          # short hex ID shown in UI
    tool_name: str          # "write_file" | "run_command"
    arguments: dict         # raw args from LLM
    display_md: str         # markdown preview shown in confirmation panel
    status: str = "pending" # "pending" | "applied" | "rejected"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PendingAction":
        return cls(**d)


# ── Ollama tool schemas ───────────────────────────────────────────────────────

AGENT_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the content of a file inside the workspace. "
                "Use this to understand existing code before proposing changes."
            ),
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to workspace root, e.g. 'src/main.py'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories at a path in the workspace.",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to workspace root. Use '.' for root.",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list recursively (default false).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files by name using a glob pattern (e.g. '**/*.py', '*.md').",
            "parameters": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py', 'src/**/*.ts', '*.md'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_code",
            "description": (
                "Search for a text pattern inside files in the workspace. "
                "Returns matching lines with file name and line number."
            ),
            "parameters": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or regex pattern to search for.",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Filter files by glob, e.g. '*.py'. Defaults to all files.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search (relative to workspace root). Defaults to '.'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file. "
                "IMPORTANT: this does NOT write immediately — the file is shown to the user "
                "for confirmation before any disk write happens."
            ),
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["write", "append"],
                        "description": "'write' = overwrite (default), 'append' = add to end.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command in the workspace. "
                "IMPORTANT: this does NOT run immediately — the command is shown to the user "
                "for confirmation first. Use for: pytest, pip install, git commands, etc."
            ),
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command, e.g. 'python -m pytest tests/ -v'",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Max seconds to wait (default 30).",
                    },
                },
            },
        },
    },
]


# ── ToolExecutor ──────────────────────────────────────────────────────────────


class ToolExecutor:
    """
    Executes agent tool calls scoped to a workspace.

    Auto tools return (result_str, None).
    Write tools return (placeholder_str, PendingAction) — NOT yet written to disk.
    """

    def __init__(self, guard: ScopeGuard) -> None:
        self.guard = guard

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def dispatch(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[str, PendingAction | None]:
        """
        Execute a tool. Returns (result_str, pending_or_None).
        Never raises — errors are returned as result_str starting with 'ERROR:'.
        """
        try:
            if tool_name == "read_file":
                return self._read_file(arguments.get("path", "")), None
            elif tool_name == "list_directory":
                return (
                    self._list_directory(
                        arguments.get("path", "."),
                        arguments.get("recursive", False),
                    ),
                    None,
                )
            elif tool_name == "search_files":
                return self._search_files(arguments.get("pattern", "*")), None
            elif tool_name == "grep_code":
                return (
                    self._grep_code(
                        arguments.get("pattern", ""),
                        arguments.get("file_glob", "*"),
                        arguments.get("path", "."),
                    ),
                    None,
                )
            elif tool_name == "write_file":
                return self._queue_write(arguments)
            elif tool_name == "run_command":
                return self._queue_command(arguments)
            else:
                return f"ERROR: Unknown tool '{tool_name}'", None
        except ScopeViolation as e:
            return f"ERROR: Path safety violation — {e}", None
        except TypeError as e:
            return f"ERROR: Bad arguments for {tool_name} — {e}", None
        except Exception as e:
            return f"ERROR: {tool_name} failed — {e}", None

    # ── Auto tool implementations ──────────────────────────────────────────────

    def _read_file(self, path: str) -> str:
        resolved = self.guard.validate(path)
        if not resolved.exists():
            return f"ERROR: File not found: {path}"
        if resolved.is_dir():
            return f"ERROR: '{path}' is a directory — use list_directory"
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"ERROR: Cannot read '{path}': {e}"
        truncated = len(content) > MAX_FILE_CHARS
        if truncated:
            content = content[:MAX_FILE_CHARS]
        lines = content.count("\n") + 1
        rel = self.guard.rel(resolved)
        note = f" [TRUNCATED at {MAX_FILE_CHARS} chars]" if truncated else ""
        return f"[File: {rel} | {lines} lines{note}]\n{content}"

    def _list_directory(self, path: str, recursive: bool = False) -> str:
        resolved = self.guard.validate(path)
        if not resolved.exists():
            return f"ERROR: Not found: {path}"
        if not resolved.is_dir():
            return f"ERROR: '{path}' is not a directory"
        entries: list[str] = []
        iter_fn = resolved.rglob("*") if recursive else resolved.iterdir()
        for item in sorted(iter_fn):
            if any(part in _SKIP_DIRS for part in item.parts):
                continue
            rel = self.guard.rel(item)
            suffix = "/" if item.is_dir() else ""
            size = ""
            if item.is_file():
                try:
                    size = f"  {item.stat().st_size:,} B"
                except OSError:
                    pass
            entries.append(f"  {rel}{suffix}{size}")
            if len(entries) >= 200:
                entries.append("  ... (truncated at 200 items)")
                break
        if not entries:
            return f"[Empty: {path}]"
        return f"[Directory: {path} | {len(entries)} items]\n" + "\n".join(entries)

    def _search_files(self, pattern: str) -> str:
        root = self.guard.root
        try:
            matches = [
                p for p in sorted(root.glob(pattern))
                if not any(part in _SKIP_DIRS for part in p.parts)
            ]
        except Exception as e:
            return f"ERROR: Invalid pattern '{pattern}': {e}"
        if not matches:
            return f"[No files match: {pattern}]"
        lines = [self.guard.rel(m) + ("/" if m.is_dir() else "") for m in matches[:150]]
        result = f"[{len(matches)} matches for '{pattern}']\n" + "\n".join(lines)
        if len(matches) > 150:
            result += f"\n... and {len(matches) - 150} more"
        return result

    def _grep_code(self, pattern: str, file_glob: str = "*", path: str = ".") -> str:
        base = self.guard.validate(path)
        if not base.is_dir():
            # treat as single file
            base_dir = base.parent
            file_glob = base.name
        else:
            base_dir = base
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"ERROR: Invalid regex '{pattern}': {e}"
        results: list[str] = []
        glob = f"**/{file_glob}" if "**" not in file_glob else file_glob
        for fpath in sorted(base_dir.rglob(file_glob)):
            if not fpath.is_file():
                continue
            if any(part in _SKIP_DIRS for part in fpath.parts):
                continue
            if fpath.stat().st_size > 500_000:
                continue
            try:
                for lineno, line in enumerate(
                    fpath.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                ):
                    if regex.search(line):
                        rel = self.guard.rel(fpath)
                        results.append(f"{rel}:{lineno}:  {line.rstrip()}")
                        if len(results) >= MAX_GREP_RESULTS:
                            results.append(f"[truncated at {MAX_GREP_RESULTS} results]")
                            break
            except Exception:
                continue
            if len(results) >= MAX_GREP_RESULTS:
                break
        if not results:
            return f"[No matches for '{pattern}' in {path}/**/{file_glob}]"
        return f"[{len(results)} matches for '{pattern}']\n" + "\n".join(results)

    # ── Write tool queueing ────────────────────────────────────────────────────

    def _queue_write(self, args: dict) -> tuple[str, PendingAction]:
        path = args.get("path", "")
        content = args.get("content", "")
        mode = args.get("mode", "write")
        # Validate path now (fail fast), but do NOT write
        try:
            resolved = self.guard.validate(path)
        except ScopeViolation as e:
            return f"ERROR: {e}", None  # type: ignore[return-value]
        rel = self.guard.rel(resolved)
        lines = content.count("\n") + 1
        size_kb = len(content.encode()) / 1024
        preview = content[:1500] + ("\n...[truncated]" if len(content) > 1500 else "")
        display_md = (
            f"**Write file** `{rel}` (mode: `{mode}`)\n\n"
            f"```\n{preview}\n```\n"
            f"*{lines} lines · {size_kb:.1f} KB*"
        )
        action = PendingAction(
            action_id=uuid.uuid4().hex[:8],
            tool_name="write_file",
            arguments={"path": str(resolved), "content": content, "mode": mode},
            display_md=display_md,
        )
        return (
            f"[PENDING write queued: {rel} ({lines} lines) — awaiting your confirmation]",
            action,
        )

    def _queue_command(self, args: dict) -> tuple[str, PendingAction]:
        command = args.get("command", "")
        timeout = int(args.get("timeout_seconds", 30))
        display_md = (
            f"**Run command** in workspace root:\n\n"
            f"```bash\n{command}\n```\n"
            f"*Timeout: {timeout}s*"
        )
        action = PendingAction(
            action_id=uuid.uuid4().hex[:8],
            tool_name="run_command",
            arguments={"command": command, "timeout_seconds": timeout},
            display_md=display_md,
        )
        return (
            f"[PENDING command queued: `{command}` — awaiting your confirmation]",
            action,
        )

    # ── Apply (called after user confirms) ────────────────────────────────────

    def apply_pending(self, action: PendingAction) -> str:
        """Execute a confirmed pending action. Returns result string."""
        if action.tool_name == "write_file":
            return self._do_write(action.arguments)
        elif action.tool_name == "run_command":
            return self._do_run(action.arguments)
        return f"ERROR: Unknown action: {action.tool_name}"

    def _do_write(self, args: dict) -> str:
        path = Path(args["path"])   # already absolute + validated when queued
        content = args["content"]
        mode = args.get("mode", "write")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if mode == "append":
                with path.open("a", encoding="utf-8") as f:
                    f.write(content)
            else:
                path.write_text(content, encoding="utf-8")
            lines = content.count("\n") + 1
            return f"Written: {self.guard.rel(path)} ({lines} lines)"
        except Exception as e:
            return f"ERROR: Write failed: {e}"

    def _do_run(self, args: dict) -> str:
        command = args["command"]
        timeout = int(args.get("timeout_seconds", 30))
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.guard.root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            if len(output) > 6000:
                output = output[:6000] + "\n...[truncated]"
            rc = result.returncode
            status = "OK" if rc == 0 else f"exit {rc}"
            return f"[{status}]\n$ {command}\n{output}"
        except subprocess.TimeoutExpired:
            return f"[TIMEOUT after {timeout}s]\n$ {command}"
        except Exception as e:
            return f"[ERROR] {e}"
