"""
Gemma 4 — Local Coding Assistant v4
Architecture (OpenClaw-inspired):
  - SOUL.md + AGENTS.md  : bootstrap memory, reloaded every turn
  - Sessions (SQLite)    : full conversation history, searchable, loadable
  - Project Memory (.md) : per-project context + wiki [[links]]
  - Plugin System        : /command interface, hot-reloadable from plugins/
  - CRON Orchestrator    : APScheduler background tasks with GUI management
  - Web Search           : SearXNG (Docker) or DuckDuckGo fallback
  - File Reader          : browse + inject project files
  - Agent Mode           : LLM autonomously reads files, proposes writes with confirmation

Tabs: Chat | Sessions | Memory | Files | Orchestrator

Run:
    ollama pull gemma4:e2b
    pip install -r requirements.txt
    python app.py   →  http://127.0.0.1:7860
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import socket
from datetime import datetime
from pathlib import Path

# Load .env before anything else (python-dotenv — no error if file missing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional; .env values can also be set as OS env vars

import gradio as gr
from gradio import ChatMessage
import ollama

import memory_manager
import session_manager
import soul_loader
from orchestrator import Orchestrator
from plugins.base import PluginContext
from plugins.loader import PluginLoader
from search import web_search
from file_tools import list_project_files, read_file_raw, format_for_chat

# Agent mode
from agent.scope_guard import ScopeGuard
from agent.tools import ToolExecutor, PendingAction
from agent.executor import (
    run_agent,
    StatusEvent, ToolCallEvent, PendingActionEvent, FinalTokenEvent, ErrorEvent,
)

# ── Global singletons (initialised once at import time) ────────────────────────

plugin_loader = PluginLoader()
_orchestrator = Orchestrator()

# ── Logging ────────────────────────────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("gemma_app")

# ── Config ─────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemma4:e2b")
EXPORT_DIR = Path("exports")
TODAY = datetime.now().strftime("%Y-%m-%d")

SYSTEM_PROMPTS: dict[str, str] = {
    "🐍 Python": """\
You are an expert Python developer.
- Use type hints and PEP 8 (max 100 chars/line)
- Prefer f-strings, list comprehensions, context managers
- Use pathlib.Path over os.path
- Explain code in 1-2 sentences BEFORE the code block
- Flag edge cases and performance issues""",

    "🗄️ SQL": """\
You are a SQL expert (SQL Server T-SQL + MySQL).
- Use CTEs instead of nested subqueries
- Add inline comments for non-obvious logic
- Always think about indexes and query performance
- SQL Server: SET NOCOUNT ON, proper transaction handling""",

    "🟨 JavaScript": """\
You are a JavaScript/TypeScript expert.
- ES2020+: async/await, optional chaining ?., nullish coalescing ??
- const/let only, never var
- Always handle errors with try/catch
- Flag XSS and injection risks in any DOM code""",

    "📊 VBA / Excel": """\
You are a VBA expert for Excel and Office automation.
- Always include: On Error GoTo ErrHandler with cleanup label
- Comment each logical block
- Specify where to place code (standard module / sheet / ThisWorkbook)
- Optimize loops: ScreenUpdating=False, Calculation=xlManual, Events=False""",

    "⚙️ WSO2 EI": """\
You are a WSO2 Enterprise Integrator expert.
- Specify which EI version you are targeting (6.x or 7.x / Micro Integrator)
- Mediation sequences: use standard mediators (log, property, callout, enrich)
- Data Services (.dbs): XML-based DSS format, validate namespace and structure
- Proxy services and REST APIs: validate XML namespace and endpoint config
- For errors: implement fault sequences with proper logging""",

    "💬 General": """\
You are a helpful, precise AI assistant.
Answer directly and concisely. For technical topics: use concrete examples.""",
}


# ── Core helpers ───────────────────────────────────────────────────────────────

def get_local_models() -> list[str]:
    try:
        response = ollama.list()
        names = [m.model for m in response.models]
        return names if names else [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL]


def _extract_text(content) -> str:
    """Safely extract plain string from Gradio 6 ChatMessage content.
    Handles both str and list[{'text':..., 'type':'text'}] formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", "") or item.get("content", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content) if content is not None else ""


def _msg_content(msg: ChatMessage) -> str:
    raw = msg.content if hasattr(msg, "content") else msg["content"]
    return _extract_text(raw)


def _msg_role(msg: ChatMessage) -> str:
    return msg.role if hasattr(msg, "role") else msg["role"]


def build_system_prompt(preset: str, project: str, search_results: str = "") -> str:
    """
    System prompt assembly order (OpenClaw pattern):
      1. SOUL.md + AGENTS.md  (bootstrap — reloaded from disk every turn)
      2. Project context       (from memory/<project>/INDEX.md)
      3. Web search results    (if search is ON)
      4. Base preset prompt    (Python / SQL / etc.)
    """
    bootstrap = soul_loader.load_bootstrap()
    base = SYSTEM_PROMPTS.get(preset, SYSTEM_PROMPTS["💬 General"])
    project_ctx = memory_manager.get_project_context(project) if project else ""

    parts: list[str] = []
    if bootstrap:
        parts.append(bootstrap)
    if project_ctx:
        parts.append(f"[PROJECT CONTEXT — {project}]\n{project_ctx}\n[/PROJECT CONTEXT]")
    if search_results:
        parts.append(
            f"[WEB SEARCH RESULTS — {TODAY}]\n{search_results}\n[/WEB SEARCH]\n\n"
            f"IMPORTANT: You have been given real-time web search results above. "
            f"Use them to answer. Do NOT say you cannot access the internet. "
            f"Always cite URLs from the results."
        )
    parts.append(base)
    return "\n\n---\n\n".join(parts)


def build_ollama_messages(
    history: list[ChatMessage], system_prompt: str
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = _msg_role(msg)
        content = _msg_content(msg)
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    return messages


# ── Export ─────────────────────────────────────────────────────────────────────

def export_md(history: list, preset: str, model: str) -> str:
    if not history:
        return "Chat is empty."
    EXPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = EXPORT_DIR / f"chat_{ts}.md"
    lines = [f"# Chat — {ts}", f"**Mode:** {preset} | **Model:** `{model}`", ""]
    for msg in history:
        role = _msg_role(msg)
        content = _msg_content(msg)
        lines += [f"**{role.capitalize()}:**", content, ""]
    fpath.write_text("\n".join(lines), encoding="utf-8")
    return f"Saved: {fpath}"


def export_json_file(history: list, preset: str, model: str) -> str:
    if not history:
        return "Chat is empty."
    EXPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = EXPORT_DIR / f"chat_{ts}.json"
    data = {
        "timestamp": ts, "model": model, "preset": preset,
        "messages": [{"role": _msg_role(m), "content": _msg_content(m)} for m in history],
    }
    fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Saved: {fpath}"


# ── Orchestrator helpers (called at UI build time) ─────────────────────────────

def _orch_task_choices() -> list[str]:
    """Display labels for the task dropdown."""
    return [
        f"{t['icon']} {t['name']} — {t.get('schedule', '?')}"
        for t in _orchestrator.tasks_summary()
    ]


def _orch_task_ids() -> list[str]:
    return [t["id"] for t in _orchestrator.get_schedule()]


def _orch_status_md() -> str:
    tasks = _orchestrator.tasks_summary()
    if not tasks:
        return "_No tasks configured._"
    lines = [
        "| Task | Schedule | Next Run | Last Status | Enabled |",
        "|---|---|---|---|---|",
    ]
    for t in tasks:
        if t.get("schedule") == "cron":
            sched = f"cron {t.get('hour', 0):02d}:{t.get('minute', 0):02d}"
        else:
            sched = f"every {t.get('interval_minutes', 60)}m"
        enabled_icon = "✅" if t.get("enabled") else "⚪"
        lines.append(
            f"| {t['name']} | {sched} | {t.get('next_run', '?')} "
            f"| {t.get('last_status', 'never')} | {enabled_icon} |"
        )
    return "\n".join(lines)


# ── Agent mode helpers ─────────────────────────────────────────────────────────

def _format_pending_md(pending: list[dict]) -> str:
    """Build markdown shown in the confirmation panel."""
    if not pending:
        return "_No pending actions._"
    parts = []
    for i, a in enumerate(pending, 1):
        icons = {"pending": "PENDING", "applied": "APPLIED", "rejected": "REJECTED"}
        icon = icons.get(a.get("status", "pending"), "?")
        parts.append(f"### Action {i} — [{icon}]\n\n{a['display_md']}")
    return "\n\n---\n\n".join(parts)


def _agent_arg_short(arguments: dict) -> str:
    """One-line argument display for tool call log."""
    parts = []
    for k, v in arguments.items():
        if k == "content":
            parts.append("content=…")
        elif isinstance(v, str) and len(v) > 30:
            parts.append(f"{k}='{v[:30]}…'")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def _bot_respond_agent(
    history: list,
    model: str,
    preset: str,
    temp: float,
    ctx: int,
    workspace_root: str,
    project: str,
    current_pending: list,
    extra_context: str,
):
    """
    Generator — handles one chat turn in Agent Mode.
    Yields 4-tuples: (history, status_text, pending_list, pending_panel_update)
    """
    import dataclasses

    user_msg = _msg_content(history[-1])
    guard = ScopeGuard(workspace_root)
    executor = ToolExecutor(guard)

    agent_instruction = (
        "\n\n---\n\n[AGENT MODE]\n"
        "You have access to file system tools. "
        "Use read_file / list_directory / search_files / grep_code to explore the workspace "
        "BEFORE answering — do not guess at file contents. "
        "Use write_file or run_command to propose changes; the user will confirm before anything "
        "is written or executed.\n"
        f"Workspace: {workspace_root}"
    )
    system_prompt = build_system_prompt(preset, project, extra_context) + agent_instruction
    messages = build_ollama_messages(history[:-1], system_prompt)
    messages.append({"role": "user", "content": user_msg})

    # Start with an empty assistant bubble
    history = list(history) + [ChatMessage(role="assistant", content="")]
    partial = ""
    new_pending = list(current_pending)

    for event in run_agent(messages, model, executor, temp, ctx):

        if isinstance(event, StatusEvent):
            yield history, event.text, new_pending, gr.update()

        elif isinstance(event, ToolCallEvent):
            # Render tool result as a Gradio "thought" bubble
            tool_bubble = ChatMessage(
                role="assistant",
                content=f"```\n{event.result_preview}\n```",
                metadata={
                    "title": f"Tool: {event.tool_name}({event.arg_preview})",
                    "status": "done",
                },
            )
            history = history[:-1] + [tool_bubble, ChatMessage(role="assistant", content=partial)]
            yield history, f"Tool: {event.tool_name}", new_pending, gr.update()

        elif isinstance(event, PendingActionEvent):
            new_pending = new_pending + [event.action.to_dict()]
            panel_md = _format_pending_md(new_pending)
            yield history, "Pending action — confirm below", new_pending, gr.update(visible=True)

        elif isinstance(event, FinalTokenEvent):
            partial += event.token
            history[-1] = ChatMessage(role="assistant", content=partial)
            yield history, "Responding…", new_pending, gr.update()

        elif isinstance(event, ErrorEvent):
            history[-1] = ChatMessage(
                role="assistant",
                content=f"**Agent error:** {event.message}",
            )
            yield history, f"Error: {event.message}", new_pending, gr.update()
            return

    log.info(f"Agent done: {len(partial)} chars, {len(new_pending)} pending")


def _task_id_from_choice(choice: str) -> str | None:
    """Resolve a display label back to a task ID via index matching."""
    choices = _orch_task_choices()
    ids = _orch_task_ids()
    if choice in choices:
        idx = choices.index(choice)
        if idx < len(ids):
            return ids[idx]
    return None


# ── UI ─────────────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    # Ensure bootstrap files exist
    soul_loader.ensure_defaults()
    memory_manager.get_projects()  # ensures memory/ dir + default project

    projects = memory_manager.get_projects()
    default_project = projects[0]
    available_models = get_local_models()
    default_model = available_models[0] if available_models else DEFAULT_MODEL

    with gr.Blocks(title="Local LLM Assistant") as demo:
        gr.Markdown("## Local LLM Assistant")

        # ── Shared state ───────────────────────────────────────────────────────
        active_project = gr.State(default_project)
        session_id_state = gr.State(session_manager.new_id())
        _save_sink = gr.State("")  # silent auto-save output
        # Agent mode state
        agent_mode_state = gr.State(False)
        workspace_root_state = gr.State("")
        pending_actions_state = gr.State([])

        # ══════════════════════════════════════════════════════════════════════
        with gr.Tabs() as main_tabs:

            # ══ TAB 1: CHAT ══════════════════════════════════════════════════
            with gr.Tab("Chat", id=0):
                with gr.Row():

                    # ── Left sidebar ───────────────────────────────────────
                    with gr.Column(scale=1, min_width=270):

                        with gr.Accordion("Model & Mode", open=False):
                            model_dd = gr.Dropdown(
                                choices=available_models, value=default_model,
                                label="Model",
                            )
                            preset_dd = gr.Dropdown(
                                choices=list(SYSTEM_PROMPTS.keys()),
                                value="🐍 Python", label="Coding Mode",
                            )
                            temperature = gr.Slider(
                                0.0, 1.0, value=0.2, step=0.05,
                                label="Temperature (low = deterministic)",
                            )
                            max_ctx = gr.Slider(
                                1024, 16384, value=4096, step=1024,
                                label="Context window (tokens)",
                                info="Lower = faster on CPU",
                            )

                        with gr.Accordion("Agent / Coding Mode", open=False):
                            agent_toggle = gr.Checkbox(
                                label="Enable Agent Mode",
                                value=False,
                                info="LLM reads files autonomously, proposes writes with confirmation",
                            )
                            workspace_input = gr.Textbox(
                                label="Workspace root directory",
                                placeholder="C:/my/project  or  /home/user/repo",
                                lines=1,
                            )
                            workspace_status = gr.Textbox(
                                label="", interactive=False, lines=1,
                                placeholder="Set workspace path to enable agent",
                            )
                            gr.Markdown(
                                "**Auto tools** (no confirmation needed):\n"
                                "`read_file` · `list_directory` · `search_files` · `grep_code`\n\n"
                                "**Write tools** (confirmation required):\n"
                                "`write_file` · `run_command`"
                            )

                        with gr.Accordion("Project Memory", open=True):
                            project_dd = gr.Dropdown(
                                choices=projects, value=default_project,
                                label="Active project",
                            )
                            project_ctx_display = gr.Textbox(
                                label="Project context",
                                value=memory_manager.get_project_context(default_project),
                                lines=3, interactive=False,
                            )

                        with gr.Accordion("Export & Session", open=False):
                            with gr.Row():
                                export_md_btn = gr.Button("Export MD", size="sm")
                                export_json_btn = gr.Button("Export JSON", size="sm")
                            export_status = gr.Textbox(
                                label="", interactive=False, lines=1,
                            )
                            gr.Markdown("*Sessions auto-saved after each response.*")
                            session_label = gr.Textbox(
                                label="Current session ID", interactive=False, lines=1,
                                value=f"New session",
                            )

                    # ── Chat area ──────────────────────────────────────────
                    with gr.Column(scale=4):
                        chatbot = gr.Chatbot(
                            height=420, label="",
                            render_markdown=True, layout="bubble",
                        )

                        # Pending actions confirmation panel (hidden by default)
                        with gr.Group(visible=False) as pending_panel:
                            gr.Markdown("### Pending Changes — Review & Confirm")
                            pending_display = gr.Markdown(value="_No pending actions._")
                            with gr.Row():
                                apply_all_btn = gr.Button(
                                    "Apply All Changes", variant="primary", size="sm", scale=3,
                                )
                                reject_all_btn = gr.Button(
                                    "Reject All", variant="stop", size="sm", scale=1,
                                )
                            pending_result = gr.Textbox(
                                label="", interactive=False, lines=1,
                                placeholder="Result of apply/reject…",
                            )

                        with gr.Row():
                            search_toggle = gr.Checkbox(
                                label="Search web",
                                value=False,
                                info="SearXNG (Docker) or DuckDuckGo fallback",
                                scale=1,
                                min_width=140,
                            )
                            search_status = gr.Textbox(
                                show_label=False, interactive=False, lines=1,
                                placeholder="Search status...",
                                scale=4,
                            )
                        msg_box = gr.Textbox(
                            placeholder="Ask a question… (Enter = send, Shift+Enter = newline)",
                            lines=3, max_lines=8,
                            show_label=False, autofocus=True,
                        )
                        with gr.Row():
                            submit_btn = gr.Button("Send", variant="primary", scale=4)
                            save_mem_btn = gr.Button("Save to memory", scale=2)
                            clear_btn = gr.Button("New session", variant="stop", scale=1)

            # ══ TAB 2: SESSIONS ══════════════════════════════════════════════
            with gr.Tab("Sessions", id=1):
                with gr.Row():

                    # ── Left: session browser ──────────────────────────────
                    with gr.Column(scale=1, min_width=270):
                        gr.Markdown("### Session Browser")
                        sess_project_filter = gr.Dropdown(
                            choices=["__all__"] + projects,
                            value="__all__",
                            label="Filter by project",
                        )
                        sess_search_box = gr.Textbox(
                            label="Search in titles/content",
                            placeholder="keyword…",
                            lines=1,
                        )
                        sess_search_btn = gr.Button("Search", size="sm")
                        sessions_dd = gr.Dropdown(
                            label="Sessions",
                            choices=session_manager.session_choices(),
                            interactive=True,
                            allow_custom_value=False,
                        )
                        with gr.Row():
                            sess_load_btn = gr.Button("Load to Chat", variant="primary", scale=2)
                            sess_delete_btn = gr.Button("Delete", variant="stop", scale=1)
                        sess_action_status = gr.Textbox(
                            label="", interactive=False, lines=1,
                        )

                    # ── Right: session detail ──────────────────────────────
                    with gr.Column(scale=3):
                        sess_meta = gr.Markdown("_Select a session to preview._")
                        sess_preview = gr.Chatbot(
                            height=420, label="Preview (read-only)",
                            render_markdown=True, layout="bubble",
                        )

            # ══ TAB 3: MEMORY ════════════════════════════════════════════════
            with gr.Tab("Memory", id=2):
                with gr.Row():

                    # ── Left: project management ───────────────────────────
                    with gr.Column(scale=1, min_width=270):
                        gr.Markdown("### Projects")
                        mem_project_dd = gr.Dropdown(
                            choices=projects, value=default_project,
                            label="Select project",
                        )
                        gr.Markdown("---")
                        gr.Markdown("**Create new project**")
                        new_proj_name = gr.Textbox(
                            label="Project name", placeholder="my_project",
                        )
                        new_proj_ctx = gr.Textbox(
                            label="Description", lines=3,
                            placeholder="What is this project about?",
                        )
                        create_proj_btn = gr.Button("Create project", variant="secondary")
                        create_proj_status = gr.Textbox(
                            label="", interactive=False, lines=1,
                        )

                    # ── Right: memory tabs ─────────────────────────────────
                    with gr.Column(scale=3):
                        with gr.Tabs():

                            with gr.Tab("Project Index"):
                                index_viewer = gr.Markdown(
                                    value=memory_manager.read_index(default_project),
                                )
                                gr.Markdown("**Edit project context (injected into every chat):**")
                                ctx_editor = gr.Textbox(
                                    label="",
                                    value=memory_manager.get_project_context(default_project),
                                    lines=5,
                                    placeholder="Describe the project — injected into every session.",
                                )
                                save_ctx_btn = gr.Button("Save context", variant="secondary")
                                ctx_save_status = gr.Textbox(
                                    label="", interactive=False, lines=1,
                                )

                            with gr.Tab("Notes"):
                                notes_dd = gr.Dropdown(
                                    label="Existing notes",
                                    choices=memory_manager.list_notes(default_project),
                                    interactive=True,
                                )
                                note_viewer = gr.Textbox(
                                    label="Note content", lines=12, interactive=False,
                                )
                                gr.Markdown("---")
                                gr.Markdown("**Add new note**")
                                new_note_title = gr.Textbox(label="Title")
                                new_note_content = gr.Textbox(label="Content", lines=6)
                                save_new_note_btn = gr.Button("Save note", variant="secondary")
                                note_save_status = gr.Textbox(
                                    label="", interactive=False, lines=1,
                                )

                            with gr.Tab("Bootstrap (SOUL / AGENTS)"):
                                gr.Markdown(
                                    "These files are **reloaded at every conversation turn** — "
                                    "they define your AI's personality and hard rules. "
                                    "Changes take effect on the next message."
                                )
                                with gr.Row():
                                    with gr.Column():
                                        gr.Markdown("**SOUL.md** — personality, style, specialization")
                                        soul_editor = gr.Textbox(
                                            label="",
                                            value=soul_loader.read_soul(),
                                            lines=15,
                                        )
                                        save_soul_btn = gr.Button("Save SOUL.md", variant="secondary")
                                        soul_save_status = gr.Textbox(
                                            label="", interactive=False, lines=1,
                                        )
                                    with gr.Column():
                                        gr.Markdown("**AGENTS.md** — always/never rules")
                                        agents_editor = gr.Textbox(
                                            label="",
                                            value=soul_loader.read_agents(),
                                            lines=15,
                                        )
                                        save_agents_btn = gr.Button("Save AGENTS.md", variant="secondary")
                                        agents_save_status = gr.Textbox(
                                            label="", interactive=False, lines=1,
                                        )

            # ══ TAB 4: FILES ═════════════════════════════════════════════════
            with gr.Tab("Files", id=3):
                with gr.Row():
                    with gr.Column(scale=1, min_width=270):
                        gr.Markdown("### File Browser")
                        dir_input = gr.Textbox(
                            label="Project directory",
                            placeholder="/path/to/your/project",
                            lines=1,
                        )
                        load_files_btn = gr.Button("Load file list", variant="secondary")
                        files_dd = gr.Dropdown(
                            label="Select file", choices=[], interactive=True,
                        )
                        inject_btn = gr.Button("Inject into chat", variant="primary")
                        inject_status = gr.Textbox(
                            label="", interactive=False, lines=2,
                        )
                    with gr.Column(scale=3):
                        file_viewer = gr.Code(
                            label="File content",
                            language="python",
                            lines=30, max_lines=60,
                            interactive=False,
                        )

            # ══ TAB 5: ORCHESTRATOR ══════════════════════════════════════════════
            with gr.Tab("Orchestrator", id=4):
                with gr.Row():

                    # ── Left: task manager ─────────────────────────────────
                    with gr.Column(scale=1, min_width=300):
                        gr.Markdown("### Task Manager")
                        orch_task_dd = gr.Dropdown(
                            label="Select task",
                            choices=_orch_task_choices(),
                            interactive=True,
                        )
                        with gr.Row():
                            orch_run_btn    = gr.Button("▶ Run Now",  variant="primary", scale=2)
                            orch_toggle_btn = gr.Button("⏯ Toggle",   scale=2)
                            orch_delete_btn = gr.Button("✕ Delete", variant="stop", scale=1)
                        orch_status = gr.Textbox(label="", interactive=False, lines=1)

                        with gr.Tabs():

                            with gr.Tab("Edit Task"):
                                orch_edit_id = gr.Textbox(
                                    label="ID (read-only)", interactive=False,
                                )
                                orch_edit_name  = gr.Textbox(label="Name")
                                orch_edit_desc  = gr.Textbox(label="Description", lines=2)
                                orch_edit_module = gr.Textbox(label="Python module")
                                orch_edit_stype = gr.Dropdown(
                                    choices=["cron", "interval"], label="Schedule type",
                                )
                                orch_edit_hour   = gr.Slider(0, 23, step=1, label="Hour (cron)")
                                orch_edit_minute = gr.Slider(0, 59, step=1, label="Minute (cron)")
                                orch_edit_interval = gr.Slider(5, 1440, step=5, label="Interval (min)")
                                orch_edit_enabled = gr.Checkbox(label="Enabled")
                                orch_edit_save_btn = gr.Button("Save Changes", variant="primary")
                                orch_edit_status = gr.Textbox(
                                    label="", interactive=False, lines=1,
                                )

                            with gr.Tab("Add New"):
                                orch_new_id    = gr.Textbox(label="ID (no spaces)", placeholder="my_task")
                                orch_new_name  = gr.Textbox(label="Name", placeholder="My Task")
                                orch_new_desc  = gr.Textbox(label="Description", lines=2)
                                orch_new_module = gr.Textbox(
                                    label="Python module",
                                    placeholder="agents.tasks.morning_brief",
                                )
                                orch_new_stype = gr.Dropdown(
                                    choices=["cron", "interval"],
                                    value="cron",
                                    label="Schedule type",
                                )
                                orch_new_hour   = gr.Slider(0, 23, value=8,  step=1, label="Hour (cron)")
                                orch_new_minute = gr.Slider(0, 59, value=50, step=1, label="Minute (cron)")
                                orch_new_interval = gr.Slider(5, 1440, value=60, step=5, label="Interval (min)")
                                orch_new_enabled = gr.Checkbox(label="Enable immediately", value=False)
                                orch_add_btn = gr.Button("Add Task", variant="secondary")
                                orch_add_status = gr.Textbox(label="", interactive=False, lines=1)

                    # ── Right: logs ────────────────────────────────────────
                    with gr.Column(scale=3):
                        with gr.Tabs():
                            with gr.Tab("Execution Log"):
                                with gr.Row():
                                    orch_log_filter = gr.Dropdown(
                                        choices=["__all__"] + _orch_task_ids(),
                                        value="__all__",
                                        label="Filter by task",
                                    )
                                    orch_refresh_btn = gr.Button("Refresh", size="sm")
                                orch_log_display = gr.Markdown(
                                    value=_orchestrator.format_runs_log(),
                                )

                            with gr.Tab("Task Detail"):
                                orch_task_detail = gr.Code(
                                    label="Task config (JSON)",
                                    language="json",
                                    lines=15, interactive=False,
                                )

                            with gr.Tab("Scheduler Status"):
                                orch_sched_status = gr.Markdown(
                                    value=_orch_status_md(),
                                )
                                orch_sched_refresh = gr.Button("Refresh", size="sm")

        # ── Event handlers ─────────────────────────────────────────────────────

        # ─ Chat: submit
        def user_submit(message: str, history: list) -> tuple[str, list]:
            return "", list(history) + [ChatMessage(role="user", content=message)]

        def bot_respond(
            history: list, model: str, preset: str, temp: float, ctx: int,
            search_on: bool, project: str, session_id: str,
            agent_mode: bool, workspace_root: str, pending_actions: list,
        ):
            user_msg = _msg_content(history[-1])
            log.info(f"User [{project}/{preset}] agent={agent_mode}: {user_msg[:80]}")

            # ── Plugin command interception (always, even in agent mode) ───────
            if plugin_loader.is_command(user_msg):
                plug_ctx = PluginContext(
                    project=project, preset=preset, model=model,
                    history=history[:-1],
                    extra={"session_id": session_id, "git_dir": ".", "orchestrator": _orchestrator},
                )
                result, is_direct = plugin_loader.execute(user_msg, plug_ctx)
                log.info(f"Plugin: {user_msg.split()[0]} → direct={is_direct}")
                if is_direct:
                    history = list(history) + [ChatMessage(role="assistant", content=result)]
                    yield history, f"Plugin: {user_msg.split()[0]}", pending_actions, gr.update()
                    return
                extra_context = result
            else:
                extra_context = ""

            # ── Agent mode ─────────────────────────────────────────────────────
            if agent_mode and workspace_root.strip():
                yield from _bot_respond_agent(
                    history, model, preset, temp, ctx,
                    workspace_root, project, pending_actions, extra_context,
                )
                return

            # ── Normal chat mode (unchanged) ───────────────────────────────────
            search_results = extra_context
            search_label = ""
            if search_on and not extra_context:
                search_label = f"Searching: {user_msg[:50]}…"
                yield list(history), search_label, pending_actions, gr.update()
                search_results = web_search(user_msg)
                hits = search_results.count("---") + 1 if "---" in search_results else 0
                search_label = f"Found {hits} results for: {user_msg[:40]}"
                log.info(f"Web search: {hits} results")

            system_prompt = build_system_prompt(preset, project, search_results)
            messages = build_ollama_messages(history[:-1], system_prompt)
            messages.append({"role": "user", "content": user_msg})

            history = list(history) + [ChatMessage(role="assistant", content="")]
            partial = ""
            try:
                stream = ollama.chat(
                    model=model, messages=messages, stream=True,
                    options={"temperature": temp, "num_ctx": ctx},
                )
                for chunk in stream:
                    token = chunk.message.content or ""
                    partial += token
                    history[-1] = ChatMessage(role="assistant", content=partial)
                    yield history, search_label, pending_actions, gr.update()
                log.info(f"Response: {len(partial)} chars")
            except ollama.ResponseError as e:
                history[-1] = ChatMessage(
                    role="assistant",
                    content=f"**Ollama error:** {e.error}\n\n`ollama pull {model}`",
                )
                yield history, search_label, pending_actions, gr.update()
            except Exception as e:
                log.error(f"bot_respond error: {e}")
                history[-1] = ChatMessage(role="assistant", content=f"**Error:** {e}")
                yield history, search_label, pending_actions, gr.update()

        def auto_save_session(
            history: list, session_id: str, project: str, preset: str, model: str
        ) -> tuple[str, str]:
            """Silently save session to SQLite after each response."""
            if not history or len(history) < 2:
                return session_id, ""
            first_user = next(
                (m for m in history if _msg_role(m) == "user"), None
            )
            title = _msg_content(first_user)[:80] if first_user else "Untitled"
            messages = [
                {"role": _msg_role(m), "content": _msg_content(m)}
                for m in history
            ]
            session_manager.save_session(session_id, project, title, preset, model, messages)
            log.info(f"Session saved: {session_id}")
            return session_id, f"Session: {session_id}"

        def save_last_to_memory(history: list, project: str) -> str:
            if len(history) < 2:
                return "Need at least one exchange to save."
            last_q = _msg_content(history[-2])
            last_a = _msg_content(history[-1])
            title = f"Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            content = f"**Q:** {last_q}\n\n**A:** {last_a}"
            path = memory_manager.save_note(project, title, content)
            return f"Saved: {path}"

        def on_project_change(project: str):
            ctx = memory_manager.get_project_context(project)
            return project, ctx

        # ─ Sessions tab
        def refresh_sessions(project_filter: str):
            proj = None if project_filter == "__all__" else project_filter
            choices = session_manager.session_choices(proj)
            return gr.update(choices=choices, value=None)

        def search_sessions_handler(query: str, project_filter: str):
            if not query.strip():
                return refresh_sessions(project_filter)
            proj = None if project_filter == "__all__" else project_filter
            results = session_manager.search_sessions(query, proj)
            choices = [(session_manager.format_label(s), s["id"]) for s in results]
            return gr.update(choices=choices, value=None)

        def on_session_select(session_id: str):
            if not session_id:
                return "_Select a session._", []
            data = session_manager.load_session(session_id)
            if not data:
                return "_Session not found._", []
            meta = (
                f"**ID:** `{data['id']}`  \n"
                f"**Project:** {data['project']}  \n"
                f"**Preset:** {data['preset']} | **Model:** `{data['model']}`  \n"
                f"**Created:** {data['created_at']}  \n"
                f"**Updated:** {data['updated_at']}  \n"
                f"**Messages:** {len(data['messages'])}"
            )
            preview_msgs = [
                ChatMessage(role=m["role"], content=m["content"])
                for m in data["messages"]
                if m["role"] in ("user", "assistant")
            ]
            return meta, preview_msgs

        def on_load_session(session_id: str):
            if not session_id:
                return [], "", "", "", "No session selected."
            data = session_manager.load_session(session_id)
            if not data:
                return [], "", "", "", "Session not found."
            msgs = [
                ChatMessage(role=m["role"], content=m["content"])
                for m in data["messages"]
                if m["role"] in ("user", "assistant")
            ]
            return (
                msgs,                    # → chatbot
                data["project"],         # → project_dd
                data["preset"],          # → preset_dd
                data["id"],              # → session_id_state
                f"Loaded session {session_id} → switch to Chat tab",
            )

        def on_delete_session(session_id: str, project_filter: str):
            if not session_id:
                return gr.update(), "No session selected."
            session_manager.delete_session(session_id)
            proj = None if project_filter == "__all__" else project_filter
            new_choices = session_manager.session_choices(proj)
            return gr.update(choices=new_choices, value=None), f"Deleted: {session_id}"

        # ─ Memory tab
        def on_mem_project_change(project: str):
            index = memory_manager.read_index(project)
            ctx = memory_manager.get_project_context(project)
            notes = memory_manager.list_notes(project)
            return index, ctx, gr.update(choices=notes, value=None), ""

        def on_create_project(name: str, description: str):
            name = name.strip()
            if not name:
                return gr.update(), gr.update(), gr.update(), "Name cannot be empty."
            memory_manager.create_project(name, description)
            all_projects = memory_manager.get_projects()
            return (
                gr.update(choices=all_projects, value=name),   # Chat project_dd
                gr.update(choices=all_projects, value=name),   # Memory mem_project_dd
                gr.update(choices=["__all__"] + all_projects), # Sessions filter
                f"Created: {name}",
            )

        def on_save_context(project: str, new_ctx: str) -> str:
            memory_manager.update_context(project, new_ctx)
            return f"Context saved for: {project}"

        def on_note_select(project: str, stem: str) -> str:
            return memory_manager.read_note(project, stem) if stem else ""

        def on_save_note(project: str, title: str, content: str):
            if not title.strip():
                return gr.update(), "Title required."
            memory_manager.save_note(project, title, content)
            notes = memory_manager.list_notes(project)
            return gr.update(choices=notes), f"Note saved in: {project}"

        def on_save_soul(content: str) -> str:
            soul_loader.write_soul(content)
            return "SOUL.md saved — effective on next message."

        def on_save_agents(content: str) -> str:
            soul_loader.write_agents(content)
            return "AGENTS.md saved — effective on next message."

        # ─ Files tab
        def on_load_files(directory: str):
            files = list_project_files(directory)
            if not files:
                return gr.update(choices=[], value=None), "No files found."
            return gr.update(choices=files, value=files[0]), f"Found {len(files)} files."

        def on_file_select(directory: str, filename: str):
            if not filename or not directory:
                return gr.update(value="", language="python")
            content, lang = read_file_raw(directory, filename)
            return gr.update(value=content, language=lang or "python")

        def on_inject_file(directory: str, filename: str, history: list):
            if not filename:
                return history, "No file selected."
            formatted = format_for_chat(directory, filename)
            msg = ChatMessage(
                role="user",
                content=f"Please review this file — `{filename}`:\n\n{formatted}",
            )
            return list(history) + [msg], f"Injected: {filename}"

        # ── Agent mode handlers ────────────────────────────────────────────────

        def on_workspace_change(workspace: str):
            ws = workspace.strip()
            if not ws:
                return "", "No workspace set"
            p = Path(ws)
            if not p.exists():
                return "", f"Path not found: {ws}"
            if not p.is_dir():
                return "", f"Not a directory: {ws}"
            resolved = str(p.resolve())
            return resolved, f"Workspace ready: {resolved}"

        def on_agent_toggle(enabled: bool, workspace_root: str):
            if enabled and not workspace_root.strip():
                return False, "Set workspace directory first"
            return enabled, ("Agent Mode ON" if enabled else "Agent Mode OFF")

        def on_apply_all(pending_actions: list, workspace_root: str):
            if not workspace_root.strip():
                return pending_actions, _format_pending_md(pending_actions), "ERROR: no workspace", gr.update()
            guard = ScopeGuard(workspace_root)
            executor = ToolExecutor(guard)
            updated = []
            results = []
            for a in pending_actions:
                if a.get("status") != "pending":
                    updated.append(a)
                    continue
                action = PendingAction.from_dict(a)
                result = executor.apply_pending(action)
                updated_a = dict(a, status="applied")
                updated.append(updated_a)
                results.append(f"`{a['tool_name']}`: {result}")
            result_text = "\n".join(results) if results else "Nothing applied."
            all_resolved = all(a.get("status") != "pending" for a in updated)
            return (
                updated,
                _format_pending_md(updated),
                result_text,
                gr.update(visible=not all_resolved),
            )

        def on_reject_all(pending_actions: list):
            updated = [dict(a, status="rejected") for a in pending_actions]
            result_text = f"Rejected {len(updated)} action(s)."
            return (
                updated,
                _format_pending_md(updated),
                result_text,
                gr.update(visible=False),
            )

        def on_clear_with_pending():
            new_sid = session_manager.new_id()
            return [], "", new_sid, f"New session: {new_sid}", [], gr.update(visible=False)

        # ── Wire events ────────────────────────────────────────────────────────

        # Workspace + agent toggle
        workspace_input.change(
            on_workspace_change,
            [workspace_input],
            [workspace_root_state, workspace_status],
        )
        agent_toggle.change(
            on_agent_toggle,
            [agent_toggle, workspace_root_state],
            [agent_mode_state, workspace_status],
        )

        # Pending panel buttons
        apply_all_btn.click(
            on_apply_all,
            [pending_actions_state, workspace_root_state],
            [pending_actions_state, pending_display, pending_result, pending_panel],
        )
        reject_all_btn.click(
            on_reject_all,
            [pending_actions_state],
            [pending_actions_state, pending_display, pending_result, pending_panel],
        )

        # Chat: submit → stream → auto-save → refresh pending display
        for trigger in [msg_box.submit, submit_btn.click]:
            trigger(
                user_submit, [msg_box, chatbot], [msg_box, chatbot], queue=False
            ).then(
                bot_respond,
                [chatbot, model_dd, preset_dd, temperature, max_ctx,
                 search_toggle, active_project, session_id_state,
                 agent_mode_state, workspace_root_state, pending_actions_state],
                [chatbot, search_status, pending_actions_state, pending_panel],
            ).then(
                lambda pa: _format_pending_md(pa),
                [pending_actions_state],
                [pending_display],
            ).then(
                auto_save_session,
                [chatbot, session_id_state, active_project, preset_dd, model_dd],
                [session_id_state, session_label],
            )

        clear_btn.click(
            on_clear_with_pending,
            outputs=[chatbot, msg_box, session_id_state, session_label,
                     pending_actions_state, pending_panel],
        )
        save_mem_btn.click(
            save_last_to_memory, [chatbot, active_project], export_status
        )
        project_dd.change(
            on_project_change, project_dd, [active_project, project_ctx_display]
        )
        export_md_btn.click(export_md, [chatbot, preset_dd, model_dd], export_status)
        export_json_btn.click(export_json_file, [chatbot, preset_dd, model_dd], export_status)

        # Sessions tab
        sess_project_filter.change(refresh_sessions, sess_project_filter, sessions_dd)
        sess_search_btn.click(
            search_sessions_handler, [sess_search_box, sess_project_filter], sessions_dd
        )
        sessions_dd.change(on_session_select, sessions_dd, [sess_meta, sess_preview])
        sess_load_btn.click(
            on_load_session, sessions_dd,
            [chatbot, project_dd, preset_dd, session_id_state, sess_action_status],
        )
        sess_delete_btn.click(
            on_delete_session, [sessions_dd, sess_project_filter],
            [sessions_dd, sess_action_status],
        )

        # Memory tab
        mem_project_dd.change(
            on_mem_project_change, mem_project_dd,
            [index_viewer, ctx_editor, notes_dd, note_viewer],
        )
        create_proj_btn.click(
            on_create_project, [new_proj_name, new_proj_ctx],
            [project_dd, mem_project_dd, sess_project_filter, create_proj_status],
        )
        save_ctx_btn.click(on_save_context, [mem_project_dd, ctx_editor], ctx_save_status)
        notes_dd.change(on_note_select, [mem_project_dd, notes_dd], note_viewer)
        save_new_note_btn.click(
            on_save_note, [mem_project_dd, new_note_title, new_note_content],
            [notes_dd, note_save_status],
        )
        save_soul_btn.click(on_save_soul, soul_editor, soul_save_status)
        save_agents_btn.click(on_save_agents, agents_editor, agents_save_status)

        # Files tab
        load_files_btn.click(on_load_files, dir_input, [files_dd, inject_status])
        files_dd.change(on_file_select, [dir_input, files_dd], file_viewer)
        inject_btn.click(
            on_inject_file, [dir_input, files_dd, chatbot], [chatbot, inject_status]
        )

        # ─ Orchestrator tab
        def on_orch_task_select(choice: str):
            tid = _task_id_from_choice(choice)
            _empty = ("", "", "", "", "cron", 8, 50, 60, False, "")
            if not tid:
                return ("",) + _empty
            tasks = _orchestrator.get_schedule()
            task = next((t for t in tasks if t["id"] == tid), None)
            if not task:
                return ("",) + _empty
            return (
                json.dumps(task, ensure_ascii=False, indent=2),  # detail JSON
                task.get("id", ""),
                task.get("name", ""),
                task.get("description", ""),
                task.get("module", ""),
                task.get("schedule", "cron"),
                task.get("hour", 8),
                task.get("minute", 50),
                task.get("interval_minutes", 60),
                task.get("enabled", False),
                "",  # clear edit status
            )

        def on_orch_edit_save(tid, name, desc, module, stype, hour, minute, interval_min, enabled):
            tid = (tid or "").strip()
            if not tid:
                return "No task selected — pick one from the dropdown.", _orch_status_md(), gr.update()
            # Preserve last_run from existing task
            existing = next(
                (t for t in _orchestrator.get_schedule() if t["id"] == tid), {}
            )
            updated = {
                "id": tid,
                "name": (name or "").strip(),
                "description": (desc or "").strip(),
                "module": (module or "").strip(),
                "schedule": stype,
                "hour": int(hour),
                "minute": int(minute),
                "interval_minutes": int(interval_min),
                "enabled": bool(enabled),
                "last_run": existing.get("last_run"),
            }
            try:
                _orchestrator.update_task(updated)
                new_choices = _orch_task_choices()
                new_ids = _orch_task_ids()
                new_val = new_choices[new_ids.index(tid)] if tid in new_ids else None
                return (
                    f"Task '{tid}' updated.",
                    _orch_status_md(),
                    gr.update(choices=new_choices, value=new_val),
                )
            except Exception as e:
                return str(e), _orch_status_md(), gr.update()

        def on_orch_run_now(choice: str):
            tid = _task_id_from_choice(choice)
            if not tid:
                return "No task selected.", _orchestrator.format_runs_log()
            result = _orchestrator.run_now(tid)
            return f"Done: {result[:200]}", _orchestrator.format_runs_log()

        def on_orch_toggle(choice: str):
            tid = _task_id_from_choice(choice)
            if not tid:
                return gr.update(), "No task selected.", _orch_status_md()
            tasks = _orchestrator.get_schedule()
            task = next((t for t in tasks if t["id"] == tid), None)
            if not task:
                return gr.update(), "Task not found.", _orch_status_md()
            new_state = not task.get("enabled", False)
            _orchestrator.set_enabled(tid, new_state)
            new_choices = _orch_task_choices()
            new_ids = _orch_task_ids()
            new_val = new_choices[new_ids.index(tid)] if tid in new_ids else None
            return (
                gr.update(choices=new_choices, value=new_val),
                f"Task '{tid}' {'enabled' if new_state else 'disabled'}.",
                _orch_status_md(),
            )

        def on_orch_delete(choice: str):
            tid = _task_id_from_choice(choice)
            if not tid:
                return gr.update(), "No task selected.", _orch_status_md()
            _orchestrator.delete_task(tid)
            new_choices = _orch_task_choices()
            new_ids = _orch_task_ids()
            return (
                gr.update(choices=new_choices, value=new_choices[0] if new_choices else None),
                f"Deleted: {tid}",
                _orch_status_md(),
            )

        def on_orch_add(tid, name, desc, module, stype, hour, minute, interval_min, enabled):
            tid = tid.strip().replace(" ", "_")
            if not tid or not name.strip():
                return "ID and Name are required.", _orch_status_md(), gr.update()
            new_task = {
                "id": tid,
                "name": name.strip(),
                "description": desc.strip(),
                "module": module.strip(),
                "schedule": stype,
                "hour": int(hour),
                "minute": int(minute),
                "interval_minutes": int(interval_min),
                "enabled": enabled,
                "last_run": None,
            }
            try:
                _orchestrator.add_task(new_task)
                new_choices = _orch_task_choices()
                new_ids = _orch_task_ids()
                new_val = new_choices[new_ids.index(tid)] if tid in new_ids else None
                return (
                    f"Task '{tid}' added.",
                    _orch_status_md(),
                    gr.update(choices=new_choices, value=new_val),
                )
            except ValueError as e:
                return str(e), _orch_status_md(), gr.update()

        def on_orch_refresh_log(filter_val: str) -> str:
            tid = None if filter_val == "__all__" else filter_val
            return _orchestrator.format_runs_log(tid)

        orch_task_dd.change(
            on_orch_task_select, orch_task_dd,
            [orch_task_detail,
             orch_edit_id, orch_edit_name, orch_edit_desc, orch_edit_module,
             orch_edit_stype, orch_edit_hour, orch_edit_minute, orch_edit_interval,
             orch_edit_enabled, orch_edit_status],
        )
        orch_edit_save_btn.click(
            on_orch_edit_save,
            [orch_edit_id, orch_edit_name, orch_edit_desc, orch_edit_module,
             orch_edit_stype, orch_edit_hour, orch_edit_minute, orch_edit_interval,
             orch_edit_enabled],
            [orch_edit_status, orch_sched_status, orch_task_dd],
        )
        orch_run_btn.click(on_orch_run_now, orch_task_dd, [orch_status, orch_log_display])
        orch_toggle_btn.click(
            on_orch_toggle, orch_task_dd,
            [orch_task_dd, orch_status, orch_sched_status],
        )
        orch_delete_btn.click(
            on_orch_delete, orch_task_dd,
            [orch_task_dd, orch_status, orch_sched_status],
        )
        orch_add_btn.click(
            on_orch_add,
            [orch_new_id, orch_new_name, orch_new_desc, orch_new_module,
             orch_new_stype, orch_new_hour, orch_new_minute, orch_new_interval,
             orch_new_enabled],
            [orch_add_status, orch_sched_status, orch_task_dd],
        )
        orch_refresh_btn.click(on_orch_refresh_log, orch_log_filter, orch_log_display)
        orch_log_filter.change(on_orch_refresh_log, orch_log_filter, orch_log_display)
        orch_sched_refresh.click(lambda: _orch_status_md(), outputs=orch_sched_status)

    return demo


# ── Entry point ────────────────────────────────────────────────────────────────

def _find_free_port(preferred: int, host: str = "127.0.0.1", tries: int = 10) -> int:
    """Return preferred port if free, otherwise next available in range."""
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return 0  # let OS assign any free port


if __name__ == "__main__":
    log.info("Starting Local LLM Assistant")
    log.info(f"Models: {get_local_models()}")
    log.info(f"Projects: {memory_manager.get_projects()}")

    _orchestrator.start()
    atexit.register(_orchestrator.stop)
    log.info("Orchestrator started")

    host = os.getenv("APP_HOST", "127.0.0.1")
    preferred_port = int(os.getenv("APP_PORT", "7860"))
    port = _find_free_port(preferred_port, host)

    if port != preferred_port:
        log.warning(f"Port {preferred_port} busy — using {port} instead")

    # Optional authentication — set APP_USERNAME + APP_PASSWORD in .env to enable
    _auth_user = os.getenv("APP_USERNAME", "")
    _auth_pass = os.getenv("APP_PASSWORD", "")
    _auth = (_auth_user, _auth_pass) if _auth_user and _auth_pass else None
    if _auth:
        log.info(f"Auth enabled for user: {_auth_user}")
    else:
        log.info("Auth disabled — set APP_USERNAME + APP_PASSWORD in .env to enable")

    demo = build_ui()
    demo.launch(
        server_name=host,
        server_port=port,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(),
        auth=_auth,
        auth_message="Local LLM Assistant — enter your credentials" if _auth else None,
    )
