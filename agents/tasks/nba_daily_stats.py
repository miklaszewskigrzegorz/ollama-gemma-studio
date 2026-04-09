"""
NBA Daily Stats — fetches yesterday's NBA scores from ESPN API (no API key required).

Schedule: cron, 08:50 daily
Output: logs/task_results/nba_YYYY-MM-DD.md

Skip logic: if the task fires more than 90 minutes after the scheduled time
(computer was off), the task is skipped — results will be fetched the next day.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path


ESPN_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    "?dates={date}&lang=en&region=us"
)

GRACE_MINUTES = 90  # skip if fired more than 90 min after scheduled time


def _check_misfire(task: dict) -> bool:
    """Returns True if the task fired too late (computer was off at scheduled time)."""
    scheduled_hour = task.get("hour", 8)
    scheduled_minute = task.get("minute", 50)
    now = datetime.now()
    scheduled_today = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    delay_minutes = (now - scheduled_today).total_seconds() / 60
    # If delay > GRACE_MINUTES → computer was off at scheduled time → skip
    return delay_minutes > GRACE_MINUTES


def _fetch_scores(target_date: date) -> list[dict]:
    """Fetches NBA scores from ESPN API for the given date."""
    url = ESPN_URL.format(date=target_date.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    events = data.get("events", [])
    results = []
    for event in events:
        name = event.get("name", "?")
        status = event.get("status", {}).get("type", {}).get("description", "?")
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        score_parts = []
        for c in sorted(competitors, key=lambda x: x.get("homeAway", ""), reverse=True):
            team = c.get("team", {}).get("displayName", "?")
            score = c.get("score", "?")
            hw = " (H)" if c.get("homeAway") == "home" else ""
            score_parts.append(f"{team}{hw}: {score}")
        results.append({
            "name": name,
            "status": status,
            "score": " | ".join(score_parts),
        })
    return results


def _format_md(games: list[dict], target_date: date) -> str:
    lines = [f"# NBA Results — {target_date.strftime('%Y-%m-%d (%A)')}", ""]
    if not games:
        lines.append("_No NBA games found for this date._")
        return "\n".join(lines)
    lines.append(f"**Games: {len(games)}**\n")
    for g in games:
        lines.append(f"### {g['name']}")
        lines.append(f"- Status: {g['status']}")
        lines.append(f"- Score: {g['score']}")
        lines.append("")
    return "\n".join(lines)


def run(task: dict) -> str:
    # Skip logic — computer was off at scheduled time
    if _check_misfire(task):
        return (
            f"[NBA_DAILY_STATS] Skipped — task fired more than {GRACE_MINUTES} min "
            f"after scheduled time {task.get('hour',8):02d}:{task.get('minute',50):02d}. "
            f"Results will be fetched tomorrow."
        )

    yesterday = date.today() - timedelta(days=1)

    try:
        games = _fetch_scores(yesterday)
    except Exception as e:
        return f"[NBA_DAILY_STATS] ESPN fetch error: {e}"

    md = _format_md(games, yesterday)

    output_dir = Path("logs/task_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    fpath = output_dir / f"nba_{yesterday.strftime('%Y-%m-%d')}.md"
    fpath.write_text(md, encoding="utf-8")

    summary = f"[NBA_DAILY_STATS] {yesterday} — {len(games)} games. Saved: {fpath}"
    if games:
        first = games[0]
        summary += f"\nFirst game: {first['name']} → {first['score']}"
    return summary
