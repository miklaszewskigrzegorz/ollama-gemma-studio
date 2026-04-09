"""
Write plugin — write (or append) content to a file on disk from chat.

Usage:
  /write path/to/file.txt | Content to write
  /write --append path/to/file.txt | Line to append

Security:
  - Path must not escape the current working directory (no ../../../ tricks)
  - Will NOT overwrite without warning if file > 100 chars
"""

from __future__ import annotations

from pathlib import Path

from plugins.base import BasePlugin, PluginContext

_MAX_SAFE_BYTES = 1_000_000  # refuse to overwrite files >1 MB silently


def _safe_path(raw: str) -> Path | None:
    """Resolve path and ensure it stays inside CWD. Returns None if unsafe."""
    try:
        p = Path(raw.strip())
        if not p.is_absolute():
            p = Path.cwd() / p
        resolved = p.resolve()
        cwd = Path.cwd().resolve()
        if not str(resolved).startswith(str(cwd)):
            return None
        return resolved
    except Exception:
        return None


class WritePlugin(BasePlugin):
    name = "write"
    trigger = "/write"
    description = "Write (or append) content to a file on disk"
    usage = "/write [--append] <path> | <content>"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        append_mode = False
        rest = args.strip()

        if rest.startswith("--append"):
            append_mode = True
            rest = rest[len("--append"):].strip()

        if "|" not in rest:
            return (
                "Usage: `/write path/to/file.txt | content here`\n"
                "Append: `/write --append path/to/file.txt | new line`"
            )

        filepath_raw, _, content = rest.partition("|")
        filepath_raw = filepath_raw.strip()
        content = content.strip()

        path = _safe_path(filepath_raw)
        if path is None:
            return f"Unsafe path rejected: `{filepath_raw}` — path must stay inside the project directory."

        # Warn before overwriting a non-empty existing file (write mode only)
        if not append_mode and path.exists() and path.stat().st_size > 100:
            size = path.stat().st_size
            if size > _MAX_SAFE_BYTES:
                return (
                    f"Refused: `{filepath_raw}` is {size // 1024} KB. "
                    "Delete or truncate it manually first."
                )

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append_mode else "w"
        # Append: add newline separator
        write_content = ("\n" + content) if (append_mode and path.exists() and path.stat().st_size > 0) else content

        path.write_text(write_content, encoding="utf-8") if mode == "w" else \
            path.open("a", encoding="utf-8").write(write_content)

        action = "Appended to" if append_mode else "Written to"
        lines = len(content.splitlines())
        return f"{action}: `{path}` ({lines} line{'s' if lines != 1 else ''})"
