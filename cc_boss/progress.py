"""Auto-append task results to PROGRESS.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import RunResult, Task

# This suffix is appended to every task prompt so CC writes to PROGRESS.md
PROGRESS_INJECTION = """

After completing this task, append a short entry to PROGRESS.md with this format:

## [{date}] {task_title}
- What was done
- Issues encountered (if any)
- Lessons learned (if any)

Keep it brief and factual — 3-5 bullet points max.
"""


def inject_progress_prompt(prompt: str) -> str:
    """Add PROGRESS.md instruction to a task prompt."""
    date = datetime.now().strftime("%Y-%m-%d")
    # Use first 60 chars of prompt as title
    title = prompt[:60].replace("\n", " ").strip()
    if len(prompt) > 60:
        title += "..."
    return prompt + PROGRESS_INJECTION.format(date=date, task_title=title)


async def append_progress(
    progress_path: str, task: Task, result: RunResult
):
    """Fallback: if CC didn't write to PROGRESS.md, we do it ourselves."""
    path = Path(progress_path)
    date = datetime.now().strftime("%Y-%m-%d")
    title = task.prompt[:60].replace("\n", " ").strip()

    entry = f"\n## [{date}] {title}\n"
    entry += f"- Status: {task.status}\n"
    if result.cost_usd:
        entry += f"- Cost: ${result.cost_usd:.4f}\n"
    if result.errors:
        entry += f"- Errors: {len(result.errors)}\n"
        for err in result.errors[:3]:
            entry += f"  - {err[:100]}\n"
    entry += "\n"

    if not path.exists():
        path.write_text("# PROGRESS\n\nAuto-generated task log.\n")
    with open(path, "a") as f:
        f.write(entry)
