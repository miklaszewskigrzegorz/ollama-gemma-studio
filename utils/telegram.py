"""
Telegram Bot sender — send messages to a Telegram chat.

Setup:
  1. Open Telegram, search for @BotFather
  2. Send /newbot, follow prompts, copy the token
  3. Add to .env:  TELEGRAM_BOT_TOKEN=123456:ABC-your-token
  4. Send any message to your bot, then run:
       python -m utils.telegram --get-chat-id
  5. Add to .env:  TELEGRAM_CHAT_ID=123456789
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 10


def _token() -> str:
    t = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not t:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Add it to .env — see utils/telegram.py for setup instructions."
        )
    return t


def _chat_id() -> str:
    c = os.getenv("TELEGRAM_CHAT_ID", "")
    if not c:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID not set. "
            "Run: python -m utils.telegram --get-chat-id"
        )
    return c


def send_message(text: str, chat_id: str | None = None, parse_mode: str = "Markdown") -> dict:
    """Send a text message. Raises RuntimeError if token/chat_id not configured."""
    token = _token()
    cid = chat_id or _chat_id()

    payload = json.dumps({
        "chat_id": cid,
        "text": text[:4096],  # Telegram message limit
        "parse_mode": parse_mode,
    }).encode()

    url = _API_BASE.format(token=token, method="sendMessage")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def get_updates() -> list[dict]:
    """Fetch recent updates — useful for finding your chat_id."""
    token = _token()
    url = _API_BASE.format(token=token, method="getUpdates")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    return data.get("result", [])


def is_configured() -> bool:
    """Return True if both token and chat_id are set in env."""
    return bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID"))


# ── CLI helper ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--get-chat-id" in sys.argv:
        print("Fetching updates from your bot...")
        updates = get_updates()
        if not updates:
            print("No messages yet. Send any message to your bot in Telegram, then re-run.")
            sys.exit(1)
        for u in updates:
            msg = u.get("message", {})
            chat = msg.get("chat", {})
            user = msg.get("from", {})
            print(f"  chat_id : {chat.get('id')}")
            print(f"  from    : {user.get('first_name')} {user.get('last_name', '')}")
            print(f"  message : {msg.get('text', '')[:60]}")
            print()
        print("Add the chat_id to .env as:  TELEGRAM_CHAT_ID=<id>")
    elif "--test" in sys.argv:
        result = send_message("Test message from Local LLM Assistant")
        print("Sent:", result.get("ok"))
    else:
        print(__doc__)
