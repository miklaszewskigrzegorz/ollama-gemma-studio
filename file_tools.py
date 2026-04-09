"""File reading utilities — browse project files and inject content into chat."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXT = {
    ".py", ".sql", ".js", ".ts", ".vba", ".bas",
    ".md", ".txt", ".json", ".yaml", ".yml",
    ".xml", ".html", ".css", ".csv", ".ini", ".toml",
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules",
    ".venv", "venv", "env", "dist", "build", ".idea", ".vscode",
}

EXT_TO_LANG: dict[str, str] = {
    ".py": "python", ".sql": "sql", ".js": "javascript",
    ".ts": "typescript", ".md": "markdown", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".html": "html",
    ".css": "css", ".xml": "xml", ".vba": "vb", ".bas": "vb",
}


def list_project_files(directory: str) -> list[str]:
    """Return relative paths of all supported files under directory."""
    base = Path(directory)
    if not base.exists() or not base.is_dir():
        return []

    files: list[str] = []
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_EXT:
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        try:
            files.append(str(f.relative_to(base)))
        except ValueError:
            files.append(str(f))
    return files


def read_file_raw(directory: str, relative_path: str) -> tuple[str, str]:
    """Read file and return (content, language) for the code viewer."""
    try:
        full = Path(directory) / relative_path
        content = full.read_text(encoding="utf-8", errors="replace")
        lang = EXT_TO_LANG.get(full.suffix.lower(), "")
        return content, lang
    except Exception as e:
        return f"Error reading file: {e}", ""


def format_for_chat(directory: str, relative_path: str) -> str:
    """Return file content formatted as a chat context block."""
    try:
        full = Path(directory) / relative_path
        content = full.read_text(encoding="utf-8", errors="replace")
        lang = EXT_TO_LANG.get(full.suffix.lower(), "")
        lines = content.count("\n") + 1
        size_kb = full.stat().st_size / 1024
        header = f"File: `{relative_path}` ({lines} lines, {size_kb:.1f} KB)"
        return f"{header}\n\n```{lang}\n{content}\n```"
    except Exception as e:
        return f"Error: {e}"
