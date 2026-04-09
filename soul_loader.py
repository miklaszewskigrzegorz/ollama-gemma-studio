"""
Bootstrap memory loader — reloaded at EVERY conversation turn.

These files are immune to context compaction because they are
read fresh from disk on each request (inspired by OpenClaw pattern).

Files:
  memory/SOUL.md    → personality, style, specialization
  memory/AGENTS.md  → always/never rules, constraints
"""

from __future__ import annotations

from pathlib import Path

MEMORY_DIR = Path("memory")


# ── Read ───────────────────────────────────────────────────────────────────────

def _read(filename: str) -> str:
    path = MEMORY_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def read_soul() -> str:
    return _read("SOUL.md")


def read_agents() -> str:
    return _read("AGENTS.md")


def load_bootstrap() -> str:
    """Combine SOUL + AGENTS into a single block for the system prompt."""
    soul = read_soul()
    rules = read_agents()
    parts: list[str] = []
    if soul:
        parts.append(f"[SOUL]\n{soul}\n[/SOUL]")
    if rules:
        parts.append(f"[AGENT RULES — ALWAYS FOLLOW]\n{rules}\n[/AGENT RULES]")
    return "\n\n".join(parts)


# ── Write ──────────────────────────────────────────────────────────────────────

def write_soul(content: str) -> None:
    MEMORY_DIR.mkdir(exist_ok=True)
    (MEMORY_DIR / "SOUL.md").write_text(content, encoding="utf-8")


def write_agents(content: str) -> None:
    MEMORY_DIR.mkdir(exist_ok=True)
    (MEMORY_DIR / "AGENTS.md").write_text(content, encoding="utf-8")


# ── Defaults ───────────────────────────────────────────────────────────────────

DEFAULT_SOUL = """\
# Soul

## Communication Style
- Respond in the language the user writes in (auto-detect)
- Be direct and concise — do not restate the question in your reply
- For code: always a brief explanation (1-2 sentences) BEFORE the code block
- Use markdown: headings, lists, fenced code blocks with language tags
- No long preambles — get straight to the point

## Profile
- Software Developer & AI Enthusiast
- Expert: Python, SQL (SQL Server T-SQL, MySQL, PostgreSQL), JavaScript, VBA
- Strong interest in: LLM integration, automation, data engineering, ETL pipelines
- Experienced with: BigQuery, REST APIs, scheduled tasks, web scraping, CI/CD

## Code Style
- Python: type hints, PEP 8, max 100 chars/line, f-strings, pathlib.Path
- SQL: CTEs over nested subqueries, index-aware, inline comments for non-obvious logic
- Always handle edge cases and None/empty inputs
"""

DEFAULT_AGENTS = """\
# Agent Rules

## Always
- Respond in the user's language (detect from their message)
- Explain code in 1-2 sentences before writing it
- Use type hints in all Python code
- Cite source URLs when using web search results
- Ask for explicit confirmation before any destructive operation

## Never
- Never perform bulk delete operations without explicit user confirmation
- Never push to git remote without user approval
- Never write SQL without considering performance (indexes, query plan)
- Never add unnecessary complexity — solve the actual problem only

## Code Quality
- Python: max 100 chars/line, f-strings, pathlib.Path (not os.path)
- SQL Server: SET NOCOUNT ON, CTEs, proper transactions
- Tests: cover edge cases and None/empty inputs
- Comments: only where the logic is non-obvious
"""


def ensure_defaults() -> None:
    """Create SOUL.md and AGENTS.md with defaults if they don't exist."""
    MEMORY_DIR.mkdir(exist_ok=True)
    soul_path = MEMORY_DIR / "SOUL.md"
    agents_path = MEMORY_DIR / "AGENTS.md"
    if not soul_path.exists():
        soul_path.write_text(DEFAULT_SOUL, encoding="utf-8")
    if not agents_path.exists():
        agents_path.write_text(DEFAULT_AGENTS, encoding="utf-8")
