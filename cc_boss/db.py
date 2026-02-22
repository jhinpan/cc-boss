"""SQLite-backed task queue and run log."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from .models import Task, TaskStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    worker_id INTEGER,
    plan TEXT,
    result_summary TEXT,
    error TEXT,
    cost_usd REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    duration_s REAL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT,
    raw_json TEXT,
    ts TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
"""


class Database:
    def __init__(self, db_path: str = "cc_boss.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def enqueue(self, prompt: str, priority: int = 0) -> Task:
        now = datetime.now().isoformat()
        cursor = await self._db.execute(
            "INSERT INTO tasks (prompt, status, priority, created_at) VALUES (?, ?, ?, ?)",
            (prompt, TaskStatus.pending.value, priority, now),
        )
        await self._db.commit()
        return Task(id=cursor.lastrowid, prompt=prompt, priority=priority, created_at=now)

    async def next_pending(self, worker_id: int | None = None) -> Task | None:
        """Atomically claim the highest-priority pending task."""
        row = await self._db.execute_fetchall(
            "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, id ASC LIMIT 1",
            (TaskStatus.pending.value,),
        )
        if not row:
            return None
        task = self._row_to_task(row[0])
        now = datetime.now().isoformat()
        await self._db.execute(
            "UPDATE tasks SET status = ?, worker_id = ?, started_at = ? WHERE id = ? AND status = ?",
            (TaskStatus.running.value, worker_id, now, task.id, TaskStatus.pending.value),
        )
        await self._db.commit()
        # Re-fetch to confirm we got it (simple optimistic lock)
        updated = await self.get_task(task.id)
        if updated and updated.status == TaskStatus.running and updated.worker_id == worker_id:
            return updated
        return None

    async def get_task(self, task_id: int) -> Task | None:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        return self._row_to_task(rows[0]) if rows else None

    async def list_tasks(self, limit: int = 50) -> list[Task]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [self._row_to_task(r) for r in rows]

    async def set_status(
        self,
        task_id: int,
        status: TaskStatus,
        result_summary: str | None = None,
        error: str | None = None,
        cost_usd: float | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        duration_s: float | None = None,
    ):
        now = datetime.now().isoformat()
        finished = now if status in (TaskStatus.done, TaskStatus.failed) else None
        await self._db.execute(
            """UPDATE tasks SET status=?, result_summary=?, error=?,
               cost_usd=?, tokens_in=?, tokens_out=?, duration_s=?,
               finished_at=? WHERE id=?""",
            (status.value, result_summary, error, cost_usd, tokens_in, tokens_out,
             duration_s, finished, task_id),
        )
        await self._db.commit()

    async def set_plan(self, task_id: int, plan: str):
        await self._db.execute(
            "UPDATE tasks SET plan=?, status=? WHERE id=?",
            (plan, TaskStatus.planned.value, task_id),
        )
        await self._db.commit()

    async def log_event(self, task_id: int, event_type: str, content: str, raw: dict):
        await self._db.execute(
            "INSERT INTO run_logs (task_id, event_type, content, raw_json, ts) VALUES (?, ?, ?, ?, ?)",
            (task_id, event_type, content, json.dumps(raw), datetime.now().isoformat()),
        )
        await self._db.commit()

    async def get_logs(self, task_id: int) -> list[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM run_logs WHERE task_id = ? ORDER BY id", (task_id,)
        )
        return [dict(r) for r in rows]

    def _row_to_task(self, row) -> Task:
        return Task(**{k: row[k] for k in row.keys()})
