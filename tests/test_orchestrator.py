"""Tests for database and orchestrator logic."""

import asyncio
import os
import tempfile

import pytest
import pytest_asyncio

from cc_boss.db import Database
from cc_boss.models import TaskStatus


@pytest_asyncio.fixture
async def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)
    await database.connect()
    yield database
    await database.close()
    os.unlink(path)


@pytest.mark.asyncio
async def test_enqueue_and_fetch(db):
    task = await db.enqueue("test prompt", priority=0)
    assert task.id is not None
    assert task.prompt == "test prompt"
    assert task.status == TaskStatus.pending


@pytest.mark.asyncio
async def test_next_pending_claims_task(db):
    await db.enqueue("task 1")
    await db.enqueue("task 2")

    claimed = await db.next_pending(worker_id=0)
    assert claimed is not None
    assert claimed.status == TaskStatus.running
    assert claimed.worker_id == 0

    # Second claim should get the next task
    claimed2 = await db.next_pending(worker_id=1)
    assert claimed2 is not None
    assert claimed2.id != claimed.id


@pytest.mark.asyncio
async def test_priority_ordering(db):
    await db.enqueue("low priority", priority=0)
    await db.enqueue("high priority", priority=10)

    claimed = await db.next_pending(worker_id=0)
    assert "high priority" in claimed.prompt


@pytest.mark.asyncio
async def test_set_status(db):
    task = await db.enqueue("test")
    await db.set_status(task.id, TaskStatus.done, result_summary="all good", cost_usd=0.01)

    updated = await db.get_task(task.id)
    assert updated.status == TaskStatus.done
    assert updated.result_summary == "all good"
    assert updated.cost_usd == 0.01
    assert updated.finished_at is not None


@pytest.mark.asyncio
async def test_plan_workflow(db):
    task = await db.enqueue("build feature X")
    await db.set_plan(task.id, "1. Do this\n2. Do that")

    updated = await db.get_task(task.id)
    assert updated.status == TaskStatus.planned
    assert "Do this" in updated.plan


@pytest.mark.asyncio
async def test_list_tasks(db):
    for i in range(5):
        await db.enqueue(f"task {i}")

    tasks = await db.list_tasks(limit=3)
    assert len(tasks) == 3


@pytest.mark.asyncio
async def test_log_event(db):
    task = await db.enqueue("test")
    await db.log_event(task.id, "assistant", "hello", {"type": "assistant"})

    logs = await db.get_logs(task.id)
    assert len(logs) == 1
    assert logs[0]["content"] == "hello"
