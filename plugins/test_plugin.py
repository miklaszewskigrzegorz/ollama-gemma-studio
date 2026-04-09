"""Test plugin — generate pytest tests via LLM for a Python file."""

from __future__ import annotations

from pathlib import Path

from plugins.base import BasePlugin, PluginContext

_MAX_CODE_CHARS = 6000


class TestPlugin(BasePlugin):
    name = "test"
    trigger = "/test"
    description = "Generate pytest tests for a Python file (uses LLM)"
    usage = "/test path/to/file.py"
    direct_result = False  # result becomes LLM context

    def run(self, args: str, ctx: PluginContext) -> str:
        fpath = args.strip()
        if not fpath:
            return "Usage: `/test path/to/file.py`"

        # Try as-is, then relative to git_dir
        path = Path(fpath)
        if not path.exists():
            alt = Path(ctx.extra.get("git_dir", ".")) / fpath
            if alt.exists():
                path = alt

        if not path.exists():
            return f"File not found: `{fpath}`\nCheck the path and try again."

        code = path.read_text(encoding="utf-8", errors="replace")
        if len(code) > _MAX_CODE_CHARS:
            code = code[:_MAX_CODE_CHARS] + f"\n... (truncated, {len(code)} total chars)"

        lines = code.count("\n") + 1
        return (
            f"Generate comprehensive **pytest** tests for this file.\n\n"
            f"**File:** `{path}` ({lines} lines)\n\n"
            f"```python\n{code}\n```\n\n"
            f"Requirements:\n"
            f"- Cover all public functions and classes\n"
            f"- Include edge cases: None, empty, boundary values\n"
            f"- Use `pytest.fixture` where appropriate\n"
            f"- Use `pytest.mark.parametrize` for data-driven cases\n"
            f"- Add docstrings to each test function\n"
            f"- Output a complete, runnable `test_{path.stem}.py` file"
        )
