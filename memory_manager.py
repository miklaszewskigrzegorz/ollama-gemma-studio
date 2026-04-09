"""
Project memory management using Markdown files with [[wiki-style]] links.

Structure:
    memory/
    ├── PROJECTS.md          ← index of all projects
    └── <project_name>/
        ├── INDEX.md         ← project context + [[note links]]
        └── notes/
            └── *.md         ← individual notes
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path("memory")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _ensure_memory() -> None:
    MEMORY_DIR.mkdir(exist_ok=True)
    projects_md = MEMORY_DIR / "PROJECTS.md"
    if not projects_md.exists():
        projects_md.write_text(
            "# Projects Index\n\n_No projects yet._\n",
            encoding="utf-8",
        )


def _index_path(project: str) -> Path:
    return MEMORY_DIR / project / "INDEX.md"


def _notes_dir(project: str) -> Path:
    return MEMORY_DIR / project / "notes"


# ── Public API ─────────────────────────────────────────────────────────────────

def get_projects() -> list[str]:
    """Return sorted list of project names. Creates 'default' if none exist."""
    _ensure_memory()
    dirs = [d.name for d in MEMORY_DIR.iterdir() if d.is_dir()]
    if not dirs:
        create_project("default", "General coding assistant workspace")
        dirs = ["default"]
    return sorted(dirs)


def create_project(name: str, description: str = "") -> None:
    """Create project directory, INDEX.md, and register in PROJECTS.md."""
    _ensure_memory()
    project_dir = MEMORY_DIR / name
    project_dir.mkdir(exist_ok=True)
    _notes_dir(name).mkdir(exist_ok=True)

    idx = _index_path(name)
    if not idx.exists():
        idx.write_text(
            f"# Project: {name}\n"
            f"Created: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"## Context\n\n{description}\n\n"
            f"## Notes\n\n",
            encoding="utf-8",
        )

    # Register in PROJECTS.md
    projects_md = MEMORY_DIR / "PROJECTS.md"
    content = projects_md.read_text(encoding="utf-8")
    link = f"- [[{name}/INDEX]] — {name}"
    if link not in content:
        content = content.replace("_No projects yet._\n", "")
        content = content.rstrip() + f"\n{link}\n"
        projects_md.write_text(content, encoding="utf-8")


def read_index(project: str) -> str:
    """Return full text of project INDEX.md."""
    idx = _index_path(project)
    if not idx.exists():
        return "_Index not found. Select or create a project._"
    return idx.read_text(encoding="utf-8")


def get_project_context(project: str) -> str:
    """Return only the ## Context section from INDEX.md."""
    idx = _index_path(project)
    if not idx.exists():
        return ""
    lines = idx.read_text(encoding="utf-8").splitlines()
    in_ctx, result = False, []
    for line in lines:
        if line.startswith("## Context"):
            in_ctx = True
            continue
        if in_ctx and line.startswith("## "):
            break
        if in_ctx:
            result.append(line)
    return "\n".join(result).strip()


def update_context(project: str, new_context: str) -> None:
    """Replace ## Context section in INDEX.md."""
    idx = _index_path(project)
    if not idx.exists():
        create_project(project)

    lines = idx.read_text(encoding="utf-8").splitlines()
    result: list[str] = []
    skip = False
    for line in lines:
        if line.startswith("## Context"):
            result += [line, "", new_context, ""]
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if not skip:
            result.append(line)
    idx.write_text("\n".join(result), encoding="utf-8")


def list_notes(project: str) -> list[str]:
    """Return sorted list of note stems (filenames without .md)."""
    nd = _notes_dir(project)
    if not nd.exists():
        return []
    return sorted([f.stem for f in nd.glob("*.md")])


def read_note(project: str, note_stem: str) -> str:
    """Return content of a note by its stem name."""
    note_path = _notes_dir(project) / f"{note_stem}.md"
    if not note_path.exists():
        return ""
    return note_path.read_text(encoding="utf-8")


def save_note(project: str, title: str, content: str) -> str:
    """Save a note, update INDEX.md ## Notes section. Returns file path."""
    create_project(project)  # ensure project exists
    nd = _notes_dir(project)
    nd.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() or c == "_" else "_" for c in title.lower())[:30]
    fname = f"{slug}_{ts}.md"
    note_path = nd / fname
    note_path.write_text(
        f"# {title}\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{content}",
        encoding="utf-8",
    )

    # Append link to INDEX.md ## Notes section
    idx = _index_path(project)
    idx_content = idx.read_text(encoding="utf-8")
    link = f"- [[notes/{note_path.stem}]] — {title}"
    if "## Notes" in idx_content:
        idx_content = idx_content.replace("## Notes\n\n", f"## Notes\n\n{link}\n")
    else:
        idx_content += f"\n## Notes\n\n{link}\n"
    idx.write_text(idx_content, encoding="utf-8")

    return str(note_path)
