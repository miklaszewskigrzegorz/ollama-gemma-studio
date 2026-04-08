# CLAUDE.md — priv_LLM Project

## Purpose
Local LLM coding assistant using **Gemma 4** via **Ollama** on a CPU-only Windows 11 laptop.
No GPU — all inference runs on CPU. Optimize for speed and minimal RAM usage.

---

## Stack
| Layer | Tool | Notes |
|---|---|---|
| LLM runtime | Ollama | Already installed locally |
| Model | `gemma4:e2b` (primary) | ~7.2 GB, best for CPU-only |
| Model (alt) | `gemma4:e4b` | ~9.6 GB, better quality |
| UI | Gradio `gr.Blocks` | Web UI on localhost:7860 |
| Language | Python 3.11+ | type hints, f-strings |

---

## How to Run

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

## Project Rules (for Claude Code)

### Python conventions in this project
- Type hints on all functions
- PEP 8 — max 100 chars per line
- f-strings only (no `.format()`)
- `pathlib.Path` over `os.path`
- `ollama.chat()` for inference — never use raw HTTP to Ollama API

### Ollama model names (actual tags from Ollama Hub)
- `gemma4:e2b` — edge 2B, 7.2 GB, 128K context
- `gemma4:e4b` — edge 4B, 9.6 GB, 128K context
- `gemma4:26b` — too large for this machine (18 GB)

### Performance tips for CPU-only
- Keep `temperature` low (0.1–0.3) for coding tasks
- Streaming responses (`stream=True`) is mandatory — never block waiting
- Do not run multiple Ollama requests in parallel on CPU
- `num_ctx` can be reduced to 4096 for faster responses if context not needed

### Gradio conventions
- Use `gr.Blocks` (not `gr.Interface`) for full layout control
- Always `queue=False` on submit events, `queue=True` on streaming bot events
- Theme: `gr.themes.Soft()`
- Port: 7860

### File structure
```
priv_LLM/
├── app.py              ← main Gradio application
├── requirements.txt
├── CLAUDE.md           ← this file
├── .gitignore
└── exports/            ← auto-created, gitignored — saved chat exports
```

---

## Coding Modes (System Prompts)
The app has preset system prompts for:
- `🐍 Python` — type hints, PEP 8, idiomatic Python
- `🗄️ SQL (T-SQL/MySQL)` — CTEs, performance, SQL Server focus
- `🟨 JavaScript` — ES2020+, async/await, security notes
- `📊 VBA / Excel` — error handling, macro placement, Office automation
- `💬 General` — concise general assistant

To add a new preset: add entry to `SYSTEM_PROMPTS` dict in `app.py`.

---

## Memory
Memory for this project lives at:
`~/.claude-firma/projects/C--cc-projects-cc_priv-priv_LLM/memory/`
