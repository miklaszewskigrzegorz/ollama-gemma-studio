"""
Gemma 4 — Local Coding Assistant
Stack: Ollama + Gradio | CPU-optimized for Windows 11 office laptop

Usage:
    ollama pull gemma4:e2b          # pull model once
    pip install -r requirements.txt
    python app.py                   # → http://127.0.0.1:7860
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import gradio as gr
import ollama

# ── Configuration ──────────────────────────────────────────────────────────────

DEFAULT_MODEL = "gemma4:e2b"
EXPORT_DIR = Path("exports")

# Coding-mode system prompts
SYSTEM_PROMPTS: dict[str, str] = {
    "🐍 Python": """\
You are an expert Python developer. When helping with code:
- Use type hints and follow PEP 8 (max 100 chars/line)
- Prefer f-strings, list comprehensions, and context managers
- Use pathlib.Path over os.path
- Always give a 1-2 sentence explanation before the code block
- Flag edge cases, potential bugs, or performance issues
- For data work: prefer pandas/polars idioms as appropriate""",

    "🗄️ SQL": """\
You are a SQL expert specializing in SQL Server (T-SQL) and MySQL.
- Write optimized, readable queries
- Use CTEs for complex logic instead of nested subqueries
- Add inline comments for non-obvious logic
- Mention relevant indexes or performance considerations
- Follow T-SQL conventions (SET NOCOUNT ON, proper transaction handling)
- For incremental patterns: always filter on updated_at or equivalent""",

    "🟨 JavaScript": """\
You are a JavaScript/TypeScript expert. Write modern, clean code:
- Use ES2020+ syntax (async/await, optional chaining ?., nullish coalescing ??)
- Prefer const/let — never var
- For async operations: always handle errors with try/catch
- Note browser compatibility concerns when relevant
- Flag XSS, injection, or prototype pollution risks in any DOM work""",

    "📊 VBA / Excel": """\
You are a VBA expert for Excel, Access, and Office automation.
- Always include error handling: On Error GoTo ErrHandler with cleanup label
- Add meaningful comments explaining each logical block
- Specify where to place code (standard module, Sheet module, ThisWorkbook)
- Note Excel version requirements for newer features (e.g. XLOOKUP = 2019+)
- Optimize loops for large datasets: turn off ScreenUpdating, Calculation, Events
- Use With blocks to reduce object references""",

    "💬 General": """\
You are a helpful, precise AI assistant.
- Be concise — answer the question directly
- For technical questions: prefer concrete examples over abstract explanations
- If the question is ambiguous, ask one clarifying question before answering""",
}


# ── Ollama helpers ─────────────────────────────────────────────────────────────

def get_local_models() -> list[str]:
    """Return Gemma 4 models available locally in Ollama."""
    try:
        response = ollama.list()
        names = [m.model for m in response.models]
        gemma = [n for n in names if "gemma4" in n.lower()]
        return gemma if gemma else [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL]


def stream_chat(
    message: str,
    history: list[tuple[str, str]],
    model: str,
    preset: str,
    temperature: float,
    max_ctx: int,
) -> str:
    """Stream a response from Ollama, yielding partial text."""
    system_prompt = SYSTEM_PROMPTS.get(preset, SYSTEM_PROMPTS["💬 General"])

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for user_msg, assistant_msg in history:
        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})
    messages.append({"role": "user", "content": message})

    partial = ""
    try:
        stream = ollama.chat(
            model=model,
            messages=messages,
            stream=True,
            options={
                "temperature": temperature,
                "num_ctx": max_ctx,
            },
        )
        for chunk in stream:
            token = chunk.message.content or ""
            partial += token
            yield partial
    except ollama.ResponseError as e:
        yield (
            f"**Ollama error:** {e.error}\n\n"
            f"Make sure the model is pulled: `ollama pull {model}`"
        )
    except Exception as e:
        yield f"**Error:** {str(e)}"


# ── Export ─────────────────────────────────────────────────────────────────────

def export_chat(history: list[tuple[str, str]], preset: str, model: str) -> str:
    """Save conversation to a markdown file in exports/."""
    if not history:
        return "Nothing to export — chat is empty."

    EXPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = EXPORT_DIR / f"chat_{ts}.md"

    lines = [
        f"# Chat Export — {ts}",
        f"**Mode:** {preset} | **Model:** `{model}`",
        "",
    ]
    for i, (user_msg, assistant_msg) in enumerate(history, 1):
        lines.append(f"### [{i}] User")
        lines.append(user_msg or "")
        lines.append("")
        lines.append(f"### [{i}] Assistant")
        lines.append(assistant_msg or "")
        lines.append("")
        lines.append("---")
        lines.append("")

    fpath.write_text("\n".join(lines), encoding="utf-8")
    return f"Saved: {fpath}"


def export_json(history: list[tuple[str, str]], preset: str, model: str) -> str:
    """Save conversation as JSON."""
    if not history:
        return "Nothing to export."
    EXPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = EXPORT_DIR / f"chat_{ts}.json"
    data = {
        "timestamp": ts,
        "model": model,
        "preset": preset,
        "messages": [
            {"role": "user", "content": u, "assistant": a}
            for u, a in history
        ],
    }
    fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Saved: {fpath}"


# ── Gradio UI ──────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    available_models = get_local_models()
    default_model = available_models[0] if available_models else DEFAULT_MODEL

    with gr.Blocks(
        title="Gemma 4 — Local Coding Assistant",
        theme=gr.themes.Soft(),
    ) as demo:

        gr.Markdown(
            "## Gemma 4 — Local Coding Assistant\n"
            "Running fully offline via Ollama · no internet required"
        )

        with gr.Row():
            # ── Left sidebar: settings ──────────────────────────────────────
            with gr.Column(scale=1, min_width=240):
                model_dd = gr.Dropdown(
                    choices=available_models,
                    value=default_model,
                    label="Model",
                    info="e2b ≈ 7 GB RAM | e4b ≈ 10 GB RAM",
                )
                preset_dd = gr.Dropdown(
                    choices=list(SYSTEM_PROMPTS.keys()),
                    value="🐍 Python",
                    label="Coding Mode",
                )
                temperature = gr.Slider(
                    minimum=0.0, maximum=1.0, value=0.2, step=0.05,
                    label="Temperature",
                    info="Low = deterministic code, High = creative",
                )
                max_ctx = gr.Slider(
                    minimum=1024, maximum=32768, value=8192, step=1024,
                    label="Context window (tokens)",
                    info="Lower = faster responses on CPU",
                )
                gr.Markdown("---")
                gr.Markdown("**Export conversation**")
                with gr.Row():
                    export_md_btn = gr.Button("Markdown", size="sm")
                    export_json_btn = gr.Button("JSON", size="sm")
                export_status = gr.Textbox(
                    label="", interactive=False, lines=1, max_lines=2
                )

            # ── Right: chat ─────────────────────────────────────────────────
            with gr.Column(scale=4):
                chatbot = gr.Chatbot(
                    height=500,
                    show_copy_button=True,
                    render_markdown=True,
                    label="",
                    bubble_full_width=False,
                )
                msg_box = gr.Textbox(
                    placeholder="Type your question… (Enter to send, Shift+Enter for newline)",
                    lines=3,
                    max_lines=8,
                    show_label=False,
                    autofocus=True,
                )
                with gr.Row():
                    submit_btn = gr.Button("Send", variant="primary", scale=3)
                    clear_btn = gr.Button("Clear chat", variant="stop", scale=1)

        # ── Event wiring ───────────────────────────────────────────────────

        def user_submit(message: str, history: list) -> tuple[str, list]:
            """Append user message and clear input."""
            return "", history + [[message, None]]

        def bot_respond(history: list, model: str, preset: str, temp: float, ctx: int):
            """Stream bot response into last history slot."""
            user_msg = history[-1][0]
            history[-1][1] = ""
            for partial in stream_chat(user_msg, history[:-1], model, preset, temp, ctx):
                history[-1][1] = partial
                yield history

        # Submit via Enter key
        msg_box.submit(
            user_submit,
            inputs=[msg_box, chatbot],
            outputs=[msg_box, chatbot],
            queue=False,
        ).then(
            bot_respond,
            inputs=[chatbot, model_dd, preset_dd, temperature, max_ctx],
            outputs=chatbot,
        )

        # Submit via button
        submit_btn.click(
            user_submit,
            inputs=[msg_box, chatbot],
            outputs=[msg_box, chatbot],
            queue=False,
        ).then(
            bot_respond,
            inputs=[chatbot, model_dd, preset_dd, temperature, max_ctx],
            outputs=chatbot,
        )

        clear_btn.click(lambda: ([], ""), outputs=[chatbot, msg_box])

        export_md_btn.click(
            export_chat,
            inputs=[chatbot, preset_dd, model_dd],
            outputs=export_status,
        )
        export_json_btn.click(
            export_json,
            inputs=[chatbot, preset_dd, model_dd],
            outputs=export_status,
        )

    return demo


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting Gemma 4 Local Coding Assistant...")
    print(f"Available models: {get_local_models()}")
    demo = build_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,       # auto-opens browser
    )
