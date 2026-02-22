"""CC subprocess runner with stream-json parsing."""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

from .config import Config
from .models import CCEvent, RunResult


class CCRunner:
    def __init__(self, config: Config):
        self.config = config

    async def run(
        self,
        prompt: str,
        repo_path: str,
        worktree_name: str | None = None,
    ) -> AsyncIterator[CCEvent]:
        """Run claude -p and yield stream-json events.

        The caller collects events; the final RunResult can be built with
        RunResult.from_events(collected).
        """
        cmd = [
            self.config.claude_cmd,
            "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "--verbose",
        ]
        if worktree_name:
            cmd += ["--worktree", worktree_name]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            async for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = CCEvent.parse_line(data)
                    yield event
                except json.JSONDecodeError:
                    # Non-JSON output (e.g. progress indicators), skip
                    continue
        finally:
            await proc.wait()


class CCMonitor:
    """Analyze CC run events and decide if follow-up is needed."""

    def analyze(self, result: RunResult) -> Diagnosis:
        errors = [e for e in result.events if e.is_error]
        if errors:
            summary = "\n".join(e.content[:200] for e in errors[:5])
            fix_prompt = (
                f"The previous task failed with these errors:\n\n{summary}\n\n"
                "Please fix these issues. Check PROGRESS.md for any prior notes on similar problems."
            )
            return Diagnosis(status="needs_fix", error_summary=summary, fix_prompt=fix_prompt)
        return Diagnosis(status="ok")


class Diagnosis:
    def __init__(self, status: str, error_summary: str = "", fix_prompt: str = ""):
        self.status = status
        self.error_summary = error_summary
        self.fix_prompt = fix_prompt
