"""Ralph Loop orchestrator — single and parallel worker modes."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from .config import Config
from .db import Database
from .models import CCEvent, RunResult, TaskStatus
from .progress import append_progress, inject_progress_prompt
from .runner import CCMonitor, CCRunner

logger = logging.getLogger(__name__)

# Type for WebSocket broadcast callback
EventCallback = Callable[[int, CCEvent], None]  # (task_id, event)


class RalphLoop:
    """Single worker loop: pull tasks, run CC, record results."""

    def __init__(
        self,
        worker_id: int,
        db: Database,
        runner: CCRunner,
        config: Config,
        on_event: EventCallback | None = None,
    ):
        self.worker_id = worker_id
        self.db = db
        self.runner = runner
        self.config = config
        self.on_event = on_event
        self.monitor = CCMonitor()
        self.current_task_id: int | None = None
        self.running = True

    async def run(self, repo_path: str, worktree_name: str | None = None):
        logger.info(f"Worker {self.worker_id} started (worktree={worktree_name})")
        while self.running:
            task = await self.db.next_pending(worker_id=self.worker_id)
            if not task:
                await asyncio.sleep(2)
                continue

            self.current_task_id = task.id
            logger.info(f"Worker {self.worker_id} picked task {task.id}: {task.prompt[:60]}")

            start = time.time()
            events: list[CCEvent] = []
            try:
                prompt = inject_progress_prompt(task.prompt)
                async for event in self.runner.run(prompt, repo_path, worktree_name):
                    events.append(event)
                    if self.on_event:
                        self.on_event(task.id, event)
                    await self.db.log_event(
                        task.id, event.type, event.content[:500], event.raw
                    )

                result = RunResult.from_events(events)
                duration = time.time() - start

                # Check if follow-up needed
                diagnosis = self.monitor.analyze(result)
                if diagnosis.status == "needs_fix":
                    await self.db.set_status(
                        task.id,
                        TaskStatus.failed,
                        error=diagnosis.error_summary[:500],
                        cost_usd=result.cost_usd,
                        tokens_in=result.tokens_in,
                        tokens_out=result.tokens_out,
                        duration_s=duration,
                    )
                    # Auto-enqueue fix task
                    await self.db.enqueue(diagnosis.fix_prompt, priority=task.priority + 1)
                    logger.info(f"Task {task.id} failed, auto-enqueued fix task")
                else:
                    await self.db.set_status(
                        task.id,
                        TaskStatus.done,
                        result_summary=result.text[:500],
                        cost_usd=result.cost_usd,
                        tokens_in=result.tokens_in,
                        tokens_out=result.tokens_out,
                        duration_s=duration,
                    )

                # Fallback progress tracking
                await append_progress(
                    str(repo_path) + "/" + self.config.progress_file, task, result
                )

            except Exception as e:
                duration = time.time() - start
                logger.exception(f"Worker {self.worker_id} error on task {task.id}")
                await self.db.set_status(
                    task.id, TaskStatus.failed, error=str(e)[:500], duration_s=duration
                )
            finally:
                self.current_task_id = None

    def stop(self):
        self.running = False


class ParallelOrchestrator:
    """Manage N RalphLoop workers, each with its own worktree."""

    def __init__(self, config: Config, db: Database, on_event: EventCallback | None = None):
        self.config = config
        self.db = db
        self.on_event = on_event
        self.workers: list[RalphLoop] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        runner = CCRunner(self.config)
        repo_path = self.config.repo_path

        for i in range(self.config.max_workers):
            wt_name = f"cc-boss-worker-{i}"
            worker = RalphLoop(
                worker_id=i,
                db=self.db,
                runner=runner,
                config=self.config,
                on_event=self.on_event,
            )
            self.workers.append(worker)
            task = asyncio.create_task(worker.run(repo_path, wt_name))
            self._tasks.append(task)

        logger.info(f"Started {self.config.max_workers} workers")

    async def stop(self):
        for w in self.workers:
            w.stop()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("All workers stopped")

    def get_worker_status(self) -> list[dict]:
        return [
            {
                "worker_id": w.worker_id,
                "current_task_id": w.current_task_id,
                "running": w.running,
            }
            for w in self.workers
        ]
