"""
Morning Brief task — generates a daily productivity summary using the LLM.

Schedule: cron, 06:00 daily
Output: logs/task_results/morning_brief_YYYY-MM-DD.md
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import ollama


def run(task: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d %A")
    model = task.get("model", "gemma4:e2b")

    prompt = (
        f"Today is {today}. Generate a concise morning brief for a software developer "
        f"and AI enthusiast working with Python, SQL, REST APIs, LLM integration, "
        f"and automation. Include:\n"
        f"1. A short motivational thought (1 sentence)\n"
        f"2. Top 3 technical areas to focus on today\n"
        f"3. One Python or SQL tip of the day\n"
        f"Keep it under 200 words. Be practical, not generic."
    )

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.7, "num_ctx": 2048},
    )
    result = response.message.content.strip()

    # Save to file
    output_dir = Path("logs/task_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    fpath = output_dir / f"morning_brief_{datetime.now().strftime('%Y-%m-%d')}.md"
    fpath.write_text(
        f"# Morning Brief — {today}\n\n{result}",
        encoding="utf-8",
    )

    return result
