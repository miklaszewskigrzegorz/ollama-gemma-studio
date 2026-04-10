"""
Agentic execution loop — handles Ollama tool calling in a multi-round loop.

Protocol:
  Round 1: send [system, history, user_msg] + tool schemas → Ollama
  If response has tool_calls:
    → execute each via ToolExecutor
    → append assistant tool-call msg + tool result msgs to history
    → repeat (Round 2, 3, ...)
  When no tool_calls in response:
    → stream final answer

Write-class tools (write_file, run_command) are NOT executed automatically.
ToolExecutor.dispatch() returns a PendingAction which is surfaced via
PendingActionEvent for the UI to buffer and show a confirmation panel.

Generator protocol:
  run_agent() yields AgentEvent objects.
  bot_respond() in app.py iterates them and updates the Gradio UI accordingly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import ollama

from agent.tools import AGENT_TOOL_SCHEMAS, PendingAction, ToolExecutor

log = logging.getLogger("agent.executor")

MAX_TOOL_ROUNDS = 10    # hard stop to prevent runaway loops


# ── Event types ───────────────────────────────────────────────────────────────

@dataclass
class StatusEvent:
    """Status line update — shown in the search_status textbox."""
    text: str


@dataclass
class ToolCallEvent:
    """A tool was called and executed (auto tools only)."""
    tool_name: str
    arg_preview: str      # short display of arguments
    result_preview: str   # first ~300 chars of the result


@dataclass
class PendingActionEvent:
    """A write-class tool was queued — user confirmation required."""
    action: PendingAction


@dataclass
class FinalTokenEvent:
    """One streaming token from the final LLM response."""
    token: str


@dataclass
class ErrorEvent:
    """An unrecoverable error occurred."""
    message: str


AgentEvent = (
    StatusEvent | ToolCallEvent | PendingActionEvent | FinalTokenEvent | ErrorEvent
)


# ── Main agent loop ───────────────────────────────────────────────────────────

def run_agent(
    messages: list[dict],
    model: str,
    executor: ToolExecutor,
    temperature: float = 0.2,
    num_ctx: int = 4096,
):
    """
    Generator — yields AgentEvent objects.

    Args:
        messages:    Complete Ollama message list [system, ...history, user].
                     Built by app.py using build_ollama_messages() + user msg.
        model:       Ollama model tag (e.g. 'gemma4:e2b').
        executor:    ToolExecutor with a configured ScopeGuard.
        temperature: LLM temperature.
        num_ctx:     Context window size in tokens.

    The caller (bot_respond in app.py) drives this generator and updates the UI.
    """
    loop_msgs = list(messages)

    for round_num in range(MAX_TOOL_ROUNDS):
        yield StatusEvent(f"Agent thinking… (round {round_num + 1})")
        log.info(f"Agent round {round_num + 1} | messages: {len(loop_msgs)}")

        # ── Call Ollama with tool schemas ──────────────────────────────────────
        try:
            response = ollama.chat(
                model=model,
                messages=loop_msgs,
                tools=AGENT_TOOL_SCHEMAS,
                stream=False,
                options={"temperature": temperature, "num_ctx": num_ctx},
            )
        except ollama.ResponseError as e:
            yield ErrorEvent(f"Ollama error: {e.error}")
            return
        except Exception as e:
            yield ErrorEvent(f"Agent loop error: {e}")
            return

        msg = response.message

        # ── No tool calls → final response ────────────────────────────────────
        if not msg.tool_calls:
            yield StatusEvent("Streaming response…")
            # If model already included content without tool_calls, yield it directly.
            # Otherwise stream a fresh final response.
            if msg.content and msg.content.strip():
                yield FinalTokenEvent(msg.content)
            else:
                yield from _stream_final(loop_msgs, model, temperature, num_ctx)
            return

        # ── Append assistant message (with tool_calls) to history ─────────────
        loop_msgs.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "function": {
                        "name": tc.function.name,
                        "arguments": dict(tc.function.arguments or {}),
                    }
                }
                for tc in msg.tool_calls
            ],
        })

        # ── Execute each tool call ─────────────────────────────────────────────
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            arguments = dict(tc.function.arguments or {})
            arg_preview = _arg_preview(arguments)

            yield StatusEvent(f"Tool: {tool_name}({arg_preview})…")
            result_str, pending = executor.dispatch(tool_name, arguments)
            log.info(f"Tool {tool_name}({arg_preview}) → {len(result_str)} chars")

            if pending is not None:
                yield PendingActionEvent(action=pending)
            else:
                yield ToolCallEvent(
                    tool_name=tool_name,
                    arg_preview=arg_preview,
                    result_preview=result_str[:300] + ("…" if len(result_str) > 300 else ""),
                )

            # Append tool result so Ollama gets it on the next round
            loop_msgs.append({
                "role": "tool",
                "content": result_str,
                "name": tool_name,
            })

    # ── Max rounds reached ────────────────────────────────────────────────────
    yield StatusEvent("Max tool rounds — finalising…")
    yield from _stream_final(loop_msgs, model, temperature, num_ctx)


def _stream_final(
    messages: list[dict],
    model: str,
    temperature: float,
    num_ctx: int,
):
    """Stream the final response after tool rounds are done."""
    try:
        stream = ollama.chat(
            model=model,
            messages=messages,
            stream=True,
            options={"temperature": temperature, "num_ctx": num_ctx},
        )
        for chunk in stream:
            token = chunk.message.content or ""
            if token:
                yield FinalTokenEvent(token)
    except ollama.ResponseError as e:
        yield ErrorEvent(f"Streaming error: {e.error}")
    except Exception as e:
        yield ErrorEvent(f"Streaming error: {e}")


def _arg_preview(args: dict) -> str:
    """Short display of tool arguments for status/log messages."""
    parts = []
    for k, v in args.items():
        if k == "content":
            parts.append("content=…")
        elif isinstance(v, str) and len(v) > 35:
            parts.append(f"{k}='{v[:35]}…'")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)
