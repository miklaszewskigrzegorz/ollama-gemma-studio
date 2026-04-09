"""
Telegram plugin — interactive setup wizard and status check.

Commands:
  /telegram status           check if Telegram is configured
  /telegram setup            step-by-step setup guide
  /telegram test             send a test message (requires token + chat_id)
  /telegram get-chat-id      fetch updates from bot to find your chat_id
"""

from __future__ import annotations

import os
from pathlib import Path

from plugins.base import BasePlugin, PluginContext

_ENV_FILE = Path(".env")


def _read_env_var(key: str) -> str:
    """Read a key from .env file directly (handles not-yet-loaded env)."""
    if not _ENV_FILE.exists():
        return os.getenv(key, "")
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"\'')
    return os.getenv(key, "")


def _write_env_var(key: str, value: str) -> str:
    """Set or update a key=value in .env. Creates the file if missing."""
    lines: list[str] = []
    found = False
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}=") and not line.strip().startswith("#"):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value  # update current process immediately
    return f"`{key}` saved to `.env`."


class TelegramPlugin(BasePlugin):
    name = "telegram"
    trigger = "/telegram"
    description = "Telegram bot setup, status check, and test message"
    usage = "/telegram status | setup | test | get-chat-id | set-token <token> | set-chatid <id>"
    direct_result = True

    def run(self, args: str, ctx: PluginContext) -> str:
        parts = args.strip().split(None, 1)
        cmd = parts[0].lower() if parts else "status"
        rest = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "status":
            return self._status()
        if cmd == "setup":
            return self._setup_guide()
        if cmd == "test":
            return self._test()
        if cmd == "get-chat-id":
            return self._get_chat_id()
        if cmd == "set-token":
            return self._set_token(rest)
        if cmd == "set-chatid":
            return self._set_chatid(rest)
        return (
            f"Unknown subcommand: `{cmd}`\n\n"
            "Usage: `/telegram status | setup | test | get-chat-id | set-token <token> | set-chatid <id>`"
        )

    # ── Subcommands ────────────────────────────────────────────────────────────

    def _status(self) -> str:
        token = _read_env_var("TELEGRAM_BOT_TOKEN")
        chat_id = _read_env_var("TELEGRAM_CHAT_ID")
        token_ok = "✅" if token else "❌"
        chatid_ok = "✅" if chat_id else "❌"
        token_display = f"`...{token[-6:]}`" if len(token) > 6 else "*(not set)*"
        chatid_display = f"`{chat_id}`" if chat_id else "*(not set)*"
        ready = token and chat_id

        lines = [
            "## Telegram Bot Status\n",
            f"| Setting | Value | OK |",
            f"|---|---|---|",
            f"| `TELEGRAM_BOT_TOKEN` | {token_display} | {token_ok} |",
            f"| `TELEGRAM_CHAT_ID`   | {chatid_display} | {chatid_ok} |",
            "",
            f"**Overall:** {'✅ Ready — run `/telegram test` to verify' if ready else '❌ Not configured — run `/telegram setup` for instructions'}",
        ]
        return "\n".join(lines)

    def _setup_guide(self) -> str:
        return """\
## Telegram Bot Setup — Step by Step

**Step 1 — Create a bot**
1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Choose a name and username for your bot
4. Copy the token (looks like `123456789:ABCdef...`)
5. Paste it here: `/telegram set-token <your-token>`

**Step 2 — Find your chat ID**
1. Send **any message** to your new bot in Telegram
2. Run: `/telegram get-chat-id`
3. Copy the `chat_id` from the output
4. Save it: `/telegram set-chatid <chat_id>`

**Step 3 — Test**
```
/telegram test
```

**Step 4 — Enable NBA task (optional)**
```
/orch enable nba_telegram
```

The NBA daily summary will be sent to your phone every morning at 08:50.
"""

    def _test(self) -> str:
        try:
            from utils.telegram import is_configured, send_message
        except ImportError as e:
            return f"Import error: {e}"

        if not is_configured():
            return "Not configured. Run `/telegram setup` first."
        try:
            result = send_message("Test message from Local LLM Assistant")
            ok = result.get("ok", False)
            return f"{'✅ Message sent!' if ok else '❌ Telegram returned ok=false'}\n\nResponse: `{result}`"
        except Exception as e:
            return f"❌ Send failed: {e}"

    def _get_chat_id(self) -> str:
        try:
            from utils.telegram import get_updates
        except ImportError as e:
            return f"Import error: {e}"

        try:
            updates = get_updates()
        except RuntimeError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"❌ API error: {e}"

        if not updates:
            return (
                "No messages found.\n\n"
                "**Send any message to your bot in Telegram** and then run `/telegram get-chat-id` again."
            )

        lines = ["## Messages found in your bot\n"]
        seen_ids: set[int] = set()
        for u in updates:
            msg = u.get("message", {})
            chat = msg.get("chat", {})
            user = msg.get("from", {})
            cid = chat.get("id")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                lines.append(
                    f"- **chat_id:** `{cid}`  "
                    f"from: {user.get('first_name', '')} {user.get('last_name', '')}  "
                    f"text: *{msg.get('text', '')[:40]}*"
                )

        if seen_ids:
            first_id = next(iter(seen_ids))
            lines += [
                "",
                f"Save your chat_id: `/telegram set-chatid {first_id}`",
            ]
        return "\n".join(lines)

    def _set_token(self, token: str) -> str:
        if not token:
            return "Usage: `/telegram set-token <your-bot-token>`"
        result = _write_env_var("TELEGRAM_BOT_TOKEN", token)
        return f"✅ {result}\nNext: send a message to your bot, then run `/telegram get-chat-id`"

    def _set_chatid(self, chat_id: str) -> str:
        if not chat_id:
            return "Usage: `/telegram set-chatid <chat_id>`"
        result = _write_env_var("TELEGRAM_CHAT_ID", chat_id)
        return f"✅ {result}\nRun `/telegram test` to verify everything works."
