"""
Read plugin — read any file from disk and inject its content into the LLM context.

Usage:
  /read path/to/file.py
  /read /absolute/path/to/config.json

Limits: max 8000 chars injected. Larger files are truncated with a warning.
"""

from __future__ import annotations

from pathlib import Path

from plugins.base import BasePlugin, PluginContext

_MAX_CHARS = 8_000


def _detect_lang(path: Path) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".sql": "sql", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".xml": "xml", ".sh": "bash", ".bat": "batch",
        ".md": "markdown", ".toml": "toml", ".ini": "ini", ".env": "bash",
        ".html": "html", ".css": "css",
    }
    return ext_map.get(path.suffix.lower(), "text")


class ReadPlugin(BasePlugin):
    name = "read"
    trigger = "/read"
    description = "Read a file from disk and inject it into the LLM context"
    usage = "/read <file-path>"
    direct_result = False  # content injected as LLM context → LLM can analyse/explain it

    def run(self, args: str, ctx: PluginContext) -> str:
        raw = args.strip()
        if not raw:
            return "Usage: `/read path/to/file.py`"

        path = Path(raw)
        if not path.is_absolute():
            # Try relative to CWD, then to git_dir
            candidates = [
                Path.cwd() / raw,
                Path(ctx.extra.get("git_dir", ".")) / raw,
            ]
            path = next((p for p in candidates if p.exists()), path)

        if not path.exists():
            return f"File not found: `{raw}`\nCheck the path and try again."

        if path.is_dir():
            files = sorted(path.iterdir())
            names = [f.name for f in files[:50]]
            note = f" (showing first 50 of {len(files)})" if len(files) > 50 else ""
            return f"Directory listing: `{path}`{note}\n\n" + "\n".join(f"- `{n}`" for n in names)

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Could not read `{raw}`: {e}"

        truncated = len(content) > _MAX_CHARS
        if truncated:
            content = content[:_MAX_CHARS]

        lang = _detect_lang(path)
        lines = content.count("\n") + 1
        header = (
            f"File: `{path}` ({lines} lines)\n"
            + (f"*(truncated to {_MAX_CHARS} chars — file is larger)*\n" if truncated else "")
        )

        return (
            f"{header}\n"
            f"```{lang}\n{content}\n```\n\n"
            f"The file content is shown above. Please analyse/explain/modify it as requested."
        )
