"""Plan mode: generate plans first, approve via UI, then execute."""

from __future__ import annotations

from .config import Config
from .db import Database
from .models import RunResult, TaskStatus
from .runner import CCRunner


PLAN_PROMPT_TEMPLATE = """You are in plan-only mode. Do NOT implement anything.
Analyze this task and produce a detailed plan in markdown:

{prompt}

Output ONLY the plan — no implementation code. Structure it as:
1. What files need to change
2. Step-by-step approach
3. Potential risks or edge cases
"""


class PlanManager:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.runner = CCRunner(config)

    async def create_plan(self, task_id: int) -> str:
        task = await self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        await self.db.set_status(task_id, TaskStatus.planning)

        plan_prompt = PLAN_PROMPT_TEMPLATE.format(prompt=task.prompt)
        events = []
        async for event in self.runner.run(plan_prompt, self.config.repo_path):
            events.append(event)

        result = RunResult.from_events(events)
        plan_text = result.text or "No plan generated."
        await self.db.set_plan(task_id, plan_text)
        return plan_text

    async def approve(self, task_id: int):
        task = await self.db.get_task(task_id)
        if not task or not task.plan:
            raise ValueError(f"Task {task_id} has no plan to approve")

        exec_prompt = (
            f"Execute this approved plan:\n\n{task.plan}\n\n"
            f"Original task: {task.prompt}"
        )
        # Re-enqueue as a high-priority execution task
        await self.db.enqueue(exec_prompt, priority=task.priority + 10)
        # Mark original as done (plan was approved)
        await self.db.set_status(task_id, TaskStatus.done, result_summary="Plan approved and enqueued for execution")

    async def reject(self, task_id: int):
        await self.db.set_status(task_id, TaskStatus.failed, error="Plan rejected")
