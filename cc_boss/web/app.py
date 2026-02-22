"""FastAPI web application."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Config
from ..db import Database
from ..models import TaskStatus
from ..orchestrator import ParallelOrchestrator
from ..planner import PlanManager
from .ws import ConnectionManager

logger = logging.getLogger(__name__)

# Globals set during lifespan
db: Database = None
orchestrator: ParallelOrchestrator = None
planner: PlanManager = None
ws_manager = ConnectionManager()


def get_config() -> Config:
    return Config(
        repo_path=os.environ.get("CCBOSS_REPO_PATH", "."),
        db_path=os.environ.get("CCBOSS_DB_PATH", "cc_boss.db"),
        max_workers=int(os.environ.get("CCBOSS_MAX_WORKERS", "5")),
        port=int(os.environ.get("CCBOSS_PORT", "8080")),
        progress_file=os.environ.get("CCBOSS_PROGRESS_FILE", "PROGRESS.md"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, orchestrator, planner
    cfg = get_config()

    db = Database(cfg.db_path)
    await db.connect()

    def on_event(task_id, event):
        asyncio.ensure_future(
            ws_manager.send_task_event(task_id, event.type, event.content[:300])
        )

    orchestrator = ParallelOrchestrator(cfg, db, on_event=on_event)
    planner = PlanManager(cfg, db)
    await orchestrator.start()

    yield

    await orchestrator.stop()
    await db.close()


app = FastAPI(title="cc-boss", lifespan=lifespan)

# Static files and templates
web_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
templates = Jinja2Templates(directory=web_dir / "templates")


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tasks = await db.list_tasks(limit=50)
    workers = orchestrator.get_worker_status()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tasks": tasks,
        "workers": workers,
    })


@app.get("/plan/{task_id}", response_class=HTMLResponse)
async def plan_page(request: Request, task_id: int):
    task = await db.get_task(task_id)
    return templates.TemplateResponse("plan.html", {
        "request": request,
        "task": task,
    })


@app.get("/logs/{task_id}", response_class=HTMLResponse)
async def logs_page(request: Request, task_id: int):
    task = await db.get_task(task_id)
    logs = await db.get_logs(task_id)
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "task": task,
        "logs": logs,
    })


# --- API ---

@app.post("/api/tasks")
async def create_task(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt required"}, status_code=400)
    priority = body.get("priority", 0)
    task = await db.enqueue(prompt, priority=priority)
    return {"id": task.id, "status": task.status}


@app.get("/api/tasks")
async def list_tasks():
    tasks = await db.list_tasks(limit=50)
    return [t.model_dump() for t in tasks]


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int):
    task = await db.get_task(task_id)
    if not task:
        return JSONResponse({"error": "not found"}, status_code=404)
    return task.model_dump()


@app.get("/api/workers")
async def get_workers():
    return orchestrator.get_worker_status()


@app.post("/api/tasks/{task_id}/plan")
async def create_plan(task_id: int):
    plan = await planner.create_plan(task_id)
    return {"task_id": task_id, "plan": plan}


@app.post("/api/tasks/{task_id}/approve")
async def approve_plan(task_id: int):
    await planner.approve(task_id)
    return {"task_id": task_id, "status": "approved"}


@app.post("/api/tasks/{task_id}/reject")
async def reject_plan(task_id: int):
    await planner.reject(task_id)
    return {"task_id": task_id, "status": "rejected"}


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
