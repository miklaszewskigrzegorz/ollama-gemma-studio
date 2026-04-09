"""
NBA Telegram Summary — fetches yesterday's NBA scores and sends to Telegram.

Schedule: cron, 08:50 daily (Warsaw time — set TZ=Europe/Warsaw in .env)
Requires: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env

Skip logic: if fired >90 min after scheduled time (computer was off) → skipped.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from utils.telegram import is_configured, send_message

ESPN_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    "?dates={date}&lang=en&region=us"
)
GRACE_MINUTES = 90


def _check_misfire(task: dict) -> bool:
    scheduled = datetime.now().replace(
        hour=task.get("hour", 8),
        minute=task.get("minute", 50),
        second=0, microsecond=0,
    )
    return (datetime.now() - scheduled).total_seconds() / 60 > GRACE_MINUTES


def _fetch_scores(target: date) -> list[dict]:
    url = ESPN_URL.format(date=target.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    results = []
    for event in data.get("events", []):
        comps = event.get("competitions", [{}])[0].get("competitors", [])
        scores = []
        for c in sorted(comps, key=lambda x: x.get("homeAway", ""), reverse=True):
            scores.append(f"{c['team']['displayName']}: {c.get('score','?')}")
        results.append({
            "name": event.get("name", "?"),
            "status": event.get("status", {}).get("type", {}).get("description", "?"),
            "score": " | ".join(scores),
        })
    return results


def _format_telegram(games: list[dict], target: date) -> str:
    header = f"*NBA Results — {target.strftime('%Y-%m-%d')}*\n_{len(games)} games_\n"
    if not games:
        return header + "\nNo games found."
    lines = [header]
    for g in games:
        lines.append(f"\n*{g['name']}*")
        lines.append(f"{g['score']}")
        lines.append(f"_{g['status']}_")
    return "\n".join(lines)


def run(task: dict) -> str:
    if _check_misfire(task):
        return (
            f"[NBA_TELEGRAM] Skipped — fired >{GRACE_MINUTES} min after scheduled time. "
            f"Resuming tomorrow at {task.get('hour',8):02d}:{task.get('minute',50):02d}."
        )

    yesterday = date.today() - timedelta(days=1)

    try:
        games = _fetch_scores(yesterday)
    except Exception as e:
        return f"[NBA_TELEGRAM] ESPN fetch error: {e}"

    msg = _format_telegram(games, yesterday)

    # Save locally regardless of Telegram status
    out_dir = Path("logs/task_results")
    out_dir.mkdir(parents=True, exist_ok=True)
    fpath = out_dir / f"nba_telegram_{yesterday}.md"
    fpath.write_text(msg, encoding="utf-8")

    # Send to Telegram
    if not is_configured():
        return (
            f"[NBA_TELEGRAM] {len(games)} games saved to {fpath}.\n"
            f"Telegram not configured — add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env.\n"
            f"Setup: python -m utils.telegram --get-chat-id"
        )

    try:
        send_message(msg)
        return f"[NBA_TELEGRAM] {yesterday} — {len(games)} games sent to Telegram. Saved: {fpath}"
    except Exception as e:
        return f"[NBA_TELEGRAM] Saved to {fpath} but Telegram failed: {e}"
