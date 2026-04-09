# CLAUDE.md — priv_LLM Project

## Purpose
Local LLM coding assistant using **Gemma 4** via **Ollama**.
All inference runs locally — no cloud API keys required.

---

## Stack

| Layer | Tool | Notes |
|---|---|---|
| LLM runtime | Ollama | Local inference server |
| Model (primary) | `gemma4:e2b` | ~7.2 GB, efficient for CPU-only |
| Model (alt) | `gemma4:e4b` | ~9.6 GB, higher quality |
| UI | Gradio `gr.Blocks` | Web UI on localhost:7860 |
| Scheduler | APScheduler | Background task orchestration |
| Storage | SQLite | Sessions and task run logs |
| Language | Python 3.11+ | Type hints, f-strings |

---

## Quick Start

```bash
# 1. Pull model (once)
ollama pull gemma4:e2b

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start app
python app.py
# → opens at http://127.0.0.1:7860
```

---

## File Structure

```
priv_LLM/
├── app.py                    ← main Gradio application
├── orchestrator.py           ← APScheduler task runner
├── session_manager.py        ← SQLite session persistence
├── soul_loader.py            ← SOUL.md + AGENTS.md loader (per-turn)
├── memory_manager.py         ← project memory (.md files)
├── search.py                 ← SearXNG (primary) + DuckDuckGo (fallback) web search
├── file_tools.py             ← file browser + chat injection
├── requirements.txt
├── CLAUDE.md                 ← this file
├── .gitignore
├── schedule.json             ← task schedule (gitignored — user-specific)
├── plugins/                  ← /command plugin system
│   ├── base.py               ← BasePlugin ABC + PluginContext
│   ├── loader.py             ← auto-discovery
│   ├── git_plugin.py         ← /git
│   ├── note_plugin.py        ← /note
│   ├── open_plugin.py        ← /open (browser + file manager)
│   ├── orch_plugin.py        ← /orch (manage Orchestrator from chat)
│   ├── read_plugin.py        ← /read (inject file into LLM context)
│   ├── search_plugin.py      ← /search
│   ├── session_plugin.py     ← /session
│   ├── telegram_plugin.py    ← /telegram setup wizard
│   ├── test_plugin.py        ← /test (generate pytest tests via LLM)
│   └── write_plugin.py       ← /write (write file from chat)
├── agents/
│   └── tasks/                ← Orchestrator task modules
│       ├── morning_brief.py  ← daily LLM productivity brief
│       ├── git_summary.py    ← periodic git status snapshot
│       ├── nba_daily_stats.py← ESPN NBA scores (example task)
│       └── nba_telegram.py   ← NBA scores → Telegram daily notification
├── utils/
│   └── telegram.py           ← Telegram Bot API wrapper (no extra deps)
├── docker/
│   └── searxng/settings.yml  ← SearXNG config (JSON output enabled)
├── docker-compose.searxng.yml← SearXNG on port 8889
├── schedule.example.json     ← example schedule (copy to schedule.json)
├── tests/                    ← pytest test suite
├── start.bat                 ← Windows launcher (auto-starts Docker + SearXNG)
├── start.sh                  ← Linux/macOS launcher
└── Makefile                  ← dev commands (make run, make test, etc.)
├── memory/                   ← project memory files (gitignored — user-specific)
│   ├── SOUL.md               ← AI personality + tool docs (reloaded every turn)
│   └── AGENTS.md             ← always/never rules (reloaded every turn)
└── logs/                     ← app.log + SQLite DB + task results (gitignored)
```

---

## Python Conventions

- Type hints on all functions
- PEP 8 — max 100 chars per line
- f-strings only (no `.format()`)
- `pathlib.Path` over `os.path`
- `ollama.chat()` for inference — never raw HTTP to Ollama API

---

## Ollama Models

| Model | Size | Context | Notes |
|---|---|---|---|
| `gemma4:e2b` | 7.2 GB | 128K | Recommended — fast on CPU |
| `gemma4:e4b` | 9.6 GB | 128K | Better quality, more RAM |
| `gemma4:27b` | ~18 GB | 128K | Requires high-end hardware |

---

## Performance Tips (CPU inference)

- Keep `temperature` at 0.1–0.3 for coding tasks
- `stream=True` is mandatory — never block waiting for full response
- Do not run multiple Ollama requests in parallel on CPU
- `num_ctx`: use 4096 for fast responses, 8192 for longer code context

---

## Gradio Conventions

- `gr.Blocks` (not `gr.Interface`)
- `queue=False` on submit, streaming via generator yielding
- Theme: `gr.themes.Soft()` passed to `launch()`
- Port: 7860

---

## Plugin System

Plugins live in `plugins/*_plugin.py`. Each must:
- Subclass `BasePlugin`
- Set `name`, `trigger` (e.g. `/myplugin`), `description`, `usage`
- Implement `run(args: str, ctx: PluginContext) -> str`
- Set `direct_result = True` (show result directly) or `False` (inject as LLM context)

Hot-reload without restart: type `/reload` in the chat.

---

## Orchestrator Tasks

Task files in `agents/tasks/<name>.py` must expose:

```python
def run(task: dict) -> str:
    ...
    return "short status string saved to DB log"
```

Register via **Orchestrator tab → Add Task** in the UI, or edit `schedule.json` directly.

---

## Coding Modes (System Prompts)

Defined in `SYSTEM_PROMPTS` dict in `app.py`:

| Preset | Focus |
|---|---|
| `🐍 Python` | Type hints, PEP 8, idiomatic Python |
| `🗄️ SQL` | CTEs, performance, SQL Server + MySQL |
| `🟨 JavaScript` | ES2020+, async/await, security notes |
| `📊 VBA / Excel` | Error handling, macro placement, Office automation |
| `⚙️ WSO2 EI` | Enterprise integration, mediation sequences, DSS |
| `💬 General` | Concise general-purpose assistant |

To add a preset: add an entry to `SYSTEM_PROMPTS` in `app.py`.
