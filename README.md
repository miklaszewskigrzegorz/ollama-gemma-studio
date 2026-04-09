# ollama-gemma-studio

**Local LLM Assistant — privacy-first AI coding assistant powered by Gemma via Ollama. 100% local, no cloud, no API keys.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)
[![Ollama](https://img.shields.io/badge/powered%20by-Ollama-black?logo=ollama)](https://ollama.com)

Everything runs on your machine. Your conversations, your code, your data — never leave your hardware.

---

## Features

- **Zero cloud dependency** — all inference via Ollama (local LLM server), no API keys required
- **Gemma 4 model** — Google's latest open-weight model (`gemma4:e2b` default, ~7 GB)
- **Multi-tab Gradio UI** — Chat, Sessions, Memory, Files, Orchestrator tabs
- **Streaming responses** — real-time token output, no waiting for full completion
- **Plugin command system** — `/git`, `/note`, `/search`, `/read`, `/write`, `/open`, `/orch`, `/telegram`, `/session`, `/test`, and more
- **Session persistence** — full conversation history in SQLite, searchable and reloadable
- **Project memory** — per-project `.md` context files injected into every conversation
- **Bootstrap soul** — `SOUL.md` + `AGENTS.md` reloaded every turn, never lost mid-session
- **Web search** — SearXNG (self-hosted Docker, aggregates 70+ sources) with DuckDuckGo fallback
- **File browser** — read any project file and inject it into chat context
- **CRON Orchestrator** — APScheduler background tasks with full GUI management
- **Telegram notifications** — daily briefs and task results pushed to your phone
- **Hot-reloadable plugins** — add or edit plugins without restarting the app
- **Coding presets** — Python, SQL, JavaScript, VBA, WSO2 EI, General expert modes
- **Windows + Linux + macOS** — launcher scripts for all three platforms

---

## Hardware Requirements

| Setup | RAM | GPU | Speed |
|---|---|---|---|
| CPU only | 8 GB | none | 2–5 tok/s, response ~30–120s |
| Recommended | 16 GB | 6 GB VRAM | 15–40 tok/s, response ~5–15s |
| Optimal | 32 GB | RTX 3080 / 4090 | 40–80 tok/s, response ~2–5s |

> **Tested on:** Windows 11 (RTX 3060, 32 GB RAM), Ubuntu 22.04 (CPU-only, 16 GB RAM), macOS M2 (Metal acceleration).  
> **Minimum:** 8 GB RAM, Python 3.11+, Ollama installed. GPU is optional but strongly recommended.

---

## Quick Start

### Windows

```bat
:: Double-click or run in Command Prompt:
start.bat
```

`start.bat` automatically creates a virtualenv, installs dependencies, starts Docker + SearXNG if available, and opens the app.

### Linux / macOS

```bash
# One command — handles everything:
make run

# Or step by step:
make setup        # create venv + install deps
make model        # pull gemma4:e2b (~7 GB)
make env          # copy .env.example → .env
make run          # start app + SearXNG
```

Opens at **http://127.0.0.1:7860**

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org/downloads) — check "Add to PATH" on Windows |
| Ollama | latest | [ollama.com](https://ollama.com) — runs as background service |
| Git | any | [git-scm.com](https://git-scm.com) |
| Docker | 20+ | Optional — only needed for SearXNG self-hosted search |

---

## Platform Setup

### Windows

```powershell
# 1. Install Python 3.12 from https://python.org/downloads
#    Check "Add Python to PATH" during install

# 2. Install Ollama from https://ollama.com/download/windows
#    Ollama runs as a Windows service automatically after install

# 3. Pull the model (in PowerShell or Command Prompt)
ollama pull gemma4:e2b

# 4. Clone and start
git clone https://github.com/miklaszewskigrzegorz/ollama-gemma-studio
cd ollama-gemma-studio
start.bat
```

> **Windows + WSL2:** Follow the Linux instructions inside your WSL terminal. Ollama running natively on Windows is accessible from WSL2 via `host.docker.internal`.

### macOS

```bash
# 1. Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install Python and Ollama
brew install python@3.12
brew install ollama

# 3. Start Ollama service
brew services start ollama

# 4. Pull the model (~7 GB download)
ollama pull gemma4:e2b

# 5. Clone and start
git clone https://github.com/miklaszewskigrzegorz/ollama-gemma-studio && cd ollama-gemma-studio
make run
```

> **Apple Silicon (M1/M2/M3):** Ollama uses Metal GPU acceleration automatically — speeds comparable to mid-range NVIDIA cards.

### Linux (Ubuntu / Debian)

```bash
# 1. Install Python 3.12
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip git

# 2. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 3. Start Ollama and pull the model
sudo systemctl enable --now ollama
ollama pull gemma4:e2b

# 4. Clone and start
git clone https://github.com/miklaszewskigrzegorz/ollama-gemma-studio && cd ollama-gemma-studio
make run
```

> **NVIDIA GPU on Linux:** Ollama detects CUDA automatically if `nvidia-container-toolkit` is installed. See [ollama.com/blog/nvidia-gpu](https://ollama.com/blog/nvidia-gpu).

---

## Manual Setup (any platform)

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows CMD
# .venv\Scripts\Activate.ps1       # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Create local config
cp .env.example .env
# Edit .env — set your timezone, ports, Telegram credentials, etc.

# Pull model
ollama pull gemma4:e2b

# Run
python app.py
```

---

## Models

| Model | Download Size | Best For |
|---|---|---|
| `gemma4:e2b` | ~7.2 GB | **Default** — fast on CPU, good quality, low RAM |
| `gemma4:e4b` | ~9.6 GB | Better reasoning, requires 16 GB+ RAM |
| `gemma4:27b` | ~18 GB | High-end hardware only, best quality |

Change the default model in `.env`:

```env
DEFAULT_MODEL=gemma4:e4b
```

---

## Configuration (.env)

Copy `.env.example` to `.env` before first run.

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_MODEL` | `gemma4:e2b` | Ollama model tag used at startup |
| `APP_PORT` | `7860` | Gradio UI port |
| `APP_HOST` | `127.0.0.1` | Bind address — set `0.0.0.0` to expose on LAN |
| `TZ` | `UTC` | Timezone for Orchestrator cron schedules (e.g. `Europe/Warsaw`) |
| `SEARXNG_URL` | *(empty)* | URL of self-hosted SearXNG instance (e.g. `http://localhost:8889`) |
| `TELEGRAM_BOT_TOKEN` | *(empty)* | Telegram Bot API token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | *(empty)* | Your Telegram chat ID for notifications |

Full list of timezone values: [Wikipedia — tz database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

---

## Plugin System

Type any command in the chat input. All plugins support `/help` for the full list.

| Command | Description | Example |
|---|---|---|
| `/help` | List all available commands with usage | `/help` |
| `/reload` | Hot-reload all plugins without restart | `/reload` |
| `/git <sub>` | Git operations: `status`, `diff`, `log`, `branch` | `/git diff` |
| `/note <Title> \| <Content>` | Save a note to project memory | `/note Meeting \| discussed auth flow` |
| `/search <query>` | Explicit web search (SearXNG or DuckDuckGo) | `/search python asyncio tutorial` |
| `/read <path>` | Read a file and inject it into LLM context | `/read app.py` |
| `/write <path> \| <content>` | Write content to a file on disk | `/write notes.md \| # TODO list` |
| `/write --append <path> \| <line>` | Append a line to an existing file | `/write --append notes.md \| - item` |
| `/open <url\|path>` | Open URL in browser or file/folder with default app | `/open https://docs.python.org` |
| `/orch list` | List all Orchestrator tasks | `/orch list` |
| `/orch run <id>` | Run a task immediately | `/orch run morning_brief` |
| `/orch enable <id>` | Enable a scheduled task | `/orch enable git_summary` |
| `/orch disable <id>` | Disable a scheduled task | `/orch disable morning_brief` |
| `/orch add ...` | Add a new task from chat | see Orchestrator section below |
| `/orch logs [id]` | Show task execution history | `/orch logs git_summary` |
| `/telegram status` | Check Telegram bot configuration | `/telegram status` |
| `/telegram setup` | Step-by-step setup guide | `/telegram setup` |
| `/telegram test` | Send a test message to your phone | `/telegram test` |
| `/telegram get-chat-id` | Fetch your chat ID from bot updates | `/telegram get-chat-id` |
| `/session list` | List recent sessions | `/session list` |
| `/session load <id>` | Load a previous conversation | `/session load abc123` |
| `/test` | Run project test suite from chat | `/test` |

### Adding a Plugin

1. Create `plugins/my_feature_plugin.py`:

```python
from plugins.base import BasePlugin, PluginContext

class MyFeaturePlugin(BasePlugin):
    name        = "my_feature"
    trigger     = "/myfeature"
    description = "One-line description shown in /help"
    usage       = "/myfeature <args>"
    direct_result = True   # True = return to chat directly; False = inject as LLM context

    def run(self, args: str, ctx: PluginContext) -> str:
        return f"You said: {args}"
```

2. Run `/reload` in chat — the plugin is live instantly, no restart needed.

The `PluginContext` object provides:

| Attribute | Type | Description |
|---|---|---|
| `ctx.project` | `str` | Active project name |
| `ctx.model` | `str` | Active Ollama model tag |
| `ctx.history` | `list` | Current conversation history |
| `ctx.preset` | `str` | Active system prompt preset |
| `ctx.extra` | `dict` | Pass-through dict (includes `orchestrator`, `git_dir`, etc.) |

---

## Orchestrator (Scheduled Tasks)

Background tasks are managed in the **Orchestrator tab** in the UI, or via `/orch` in chat.

### Built-in tasks (disabled by default)

| Task ID | Schedule | Description |
|---|---|---|
| `morning_brief` | Daily 06:00 | AI-generated productivity summary sent via Telegram |
| `git_summary` | Every 2 hours | Git status snapshot saved to logs |

### Enable a task

```
/orch enable morning_brief
```

### Add a custom task from chat

```
/orch add id=price_check name="Price Checker" module=agents.tasks.price_check schedule=interval interval=30
```

```
/orch add id=daily_report name="Daily Report" module=agents.tasks.daily_report schedule=cron hour=8 minute=30 enabled=true
```

### Write a custom task module

```python
# agents/tasks/my_task.py

def run(task: dict) -> str:
    """
    Called by the Orchestrator on schedule.
    task dict = the full config entry from schedule.json.
    Return a short status string (stored in the run log).
    """
    # your logic here — query APIs, read files, call Ollama, send Telegram, etc.
    return "task completed successfully"
```

Register it:
- **UI:** Orchestrator tab → Add Task
- **Chat:** `/orch add id=my_task name="My Task" module=agents.tasks.my_task schedule=cron hour=9 minute=0`

Task run history is stored in `logs/app.db` (table `task_runs`) and viewable via `/orch logs`.

---

## Web Search — SearXNG (optional)

By default the app uses **DuckDuckGo** (no setup required, no API key).

For richer results, run **SearXNG** locally — it aggregates Google, Bing, DuckDuckGo, and 70+ sources simultaneously.

```bash
# Start SearXNG (Docker required)
docker compose -f docker-compose.searxng.yml up -d

# Verify
curl http://localhost:8889/healthz

# Enable in .env
echo "SEARXNG_URL=http://localhost:8889" >> .env

# Stop
docker compose -f docker-compose.searxng.yml down
```

The app automatically falls back to DuckDuckGo if SearXNG is unreachable.

---

## Telegram Notifications

Get daily briefs and task results pushed to your phone.

```
# In the chat:
/telegram setup        <- follow the 4-step wizard
/telegram test         <- verify it works
```

Step-by-step:
1. Create a bot via [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token → `/telegram set-token <token>`
3. Send any message to your bot → `/telegram get-chat-id`
4. Save the ID → `/telegram set-chatid <id>`
5. Test → `/telegram test`
6. Enable morning brief → `/orch enable morning_brief`

Telegram uses only Python's built-in `urllib` — no extra dependencies.

---

## Project Structure

```
ollama-gemma-studio/
├── app.py                      Main Gradio application
├── orchestrator.py             APScheduler task runner + schedule.json manager
├── session_manager.py          SQLite session persistence
├── soul_loader.py              SOUL.md + AGENTS.md loader (reloaded every turn)
├── memory_manager.py           Per-project .md memory files
├── search.py                   Web search (SearXNG primary, DuckDuckGo fallback)
├── file_tools.py               File browser + chat injection
│
├── plugins/                    /command plugin system
│   ├── base.py                 BasePlugin ABC + PluginContext dataclass
│   ├── loader.py               Auto-discovery of *_plugin.py files
│   ├── git_plugin.py           /git — git status, diff, log, branch
│   ├── note_plugin.py          /note — save notes to project memory
│   ├── search_plugin.py        /search — explicit web search
│   ├── read_plugin.py          /read — read file into LLM context
│   ├── write_plugin.py         /write — write file from chat
│   ├── open_plugin.py          /open — open URL or file
│   ├── orch_plugin.py          /orch — manage Orchestrator tasks
│   ├── telegram_plugin.py      /telegram — setup wizard + test
│   ├── session_plugin.py       /session — list/load saved sessions
│   └── test_plugin.py          /test — run test suite from chat
│
├── agents/tasks/               Orchestrator task modules
│   ├── morning_brief.py        Daily AI productivity summary
│   └── git_summary.py          Git status snapshot
│
├── utils/
│   └── telegram.py             Telegram Bot API wrapper (urllib only)
│
├── docker/searxng/             SearXNG Docker configuration
├── docker-compose.searxng.yml  SearXNG on port 8889
│
├── tests/                      Pytest test suite
│   ├── conftest.py
│   ├── test_search.py
│   ├── test_plugins.py
│   └── test_orchestrator.py
│
├── memory/                     Per-project memory files (.md)
├── logs/                       app.log + app.db (SQLite)
├── exports/                    Exported chat sessions
├── schedule.json               Orchestrator task config (auto-created)
│
├── SOUL.md                     Bootstrap personality / system instructions
├── AGENTS.md                   Agent mode definitions
│
├── start.sh                    Quick launcher — Linux / macOS
├── start.bat                   Quick launcher — Windows
├── Makefile                    Dev commands (Linux / macOS)
├── requirements.txt
├── .env.example                Config template (committed)
└── .env                        Local secrets (gitignored)
```

---

## Development

### Run tests

```bash
# Linux / macOS
make test

# Windows or any platform
.venv/Scripts/activate && pytest tests/ -v

# With coverage report
pytest tests/ -v --tb=short
```

### Makefile targets (Linux / macOS)

| Target | Description |
|---|---|
| `make setup` | Create venv + install dependencies |
| `make run` | Start app + SearXNG |
| `make test` | Run pytest suite |
| `make model` | Pull default Ollama model |
| `make update` | Upgrade all Python dependencies |
| `make clean` | Remove venv and cache files |
| `make backup` | Archive memory, logs, schedule.json |
| `make search-up` | Start SearXNG Docker container |
| `make search-down` | Stop SearXNG Docker container |

---

## Troubleshooting

**`ollama: command not found`**
- macOS: `brew link ollama` or restart terminal
- Linux: re-run `curl -fsSL https://ollama.com/install.sh | sh`
- Windows: restart Command Prompt after Ollama install

**`Connection refused` to Ollama**
```bash
ollama serve                          # macOS / Linux (foreground)
brew services start ollama            # macOS (background)
sudo systemctl start ollama           # Linux (systemd)
# Windows: Ollama runs as a Windows service — check Task Manager → Services
```

**Port 7860 already in use**
```env
APP_PORT=7861
```

**App starts but model is slow**
- `gemma4:e2b` needs ~8 GB free RAM
- Lower the context window in the UI slider (4096 = fastest)
- Close other memory-heavy applications

**`ModuleNotFoundError`**
```bash
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**SearXNG returns no results**
```bash
docker ps | grep searxng
docker compose -f docker-compose.searxng.yml logs
```

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -r requirements.txt`
4. Add tests in `tests/` for any new behaviour
5. Run the test suite: `pytest tests/ -v`
6. Submit a pull request — PRs Welcome!

Please keep pull requests focused. One feature or fix per PR.

---

## License

MIT — see [LICENSE](LICENSE) for full text.

---

## Acknowledgements

- [Ollama](https://ollama.com) — local LLM inference engine
- [Google Gemma](https://ai.google.dev/gemma) — open-weight model
- [Gradio](https://gradio.app) — web UI framework
- [SearXNG](https://searxng.github.io/searxng/) — self-hosted metasearch engine
- [APScheduler](https://apscheduler.readthedocs.io) — background task scheduling

---

*Built with [Claude Code](https://claude.ai/claude-code)*
