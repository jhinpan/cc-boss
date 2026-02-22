"""CLI entry point: cc-boss start / add / status."""

from __future__ import annotations

import asyncio

import click
import uvicorn

from .config import Config


@click.group()
def cli():
    """cc-boss: Orchestrate multiple Claude Code instances."""
    pass


@cli.command()
@click.option("--port", default=8080, help="Web UI port")
@click.option("--workers", default=5, help="Number of parallel CC workers")
@click.option("--repo", default=".", help="Path to the git repo to work on")
@click.option("--db", "db_path", default="cc_boss.db", help="SQLite database path")
@click.option("--config", "config_path", default=None, help="YAML config file")
def start(port: int, workers: int, repo: str, db_path: str, config_path: str | None):
    """Start the cc-boss web server and workers."""
    cfg = Config.from_cli(
        port=port, max_workers=workers, repo_path=repo, db_path=db_path, config=config_path
    )

    # Store config in environment for FastAPI to pick up
    import os
    os.environ["CCBOSS_REPO_PATH"] = cfg.repo_path
    os.environ["CCBOSS_DB_PATH"] = cfg.db_path
    os.environ["CCBOSS_MAX_WORKERS"] = str(cfg.max_workers)
    os.environ["CCBOSS_PORT"] = str(cfg.port)
    os.environ["CCBOSS_PROGRESS_FILE"] = cfg.progress_file

    click.echo(f"Starting cc-boss on port {port} with {workers} workers")
    click.echo(f"Repo: {repo}")
    click.echo(f"DB: {db_path}")

    uvicorn.run(
        "cc_boss.web.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


@cli.command()
@click.argument("prompt")
@click.option("--db", "db_path", default="cc_boss.db")
@click.option("--priority", default=0)
def add(prompt: str, db_path: str, priority: int):
    """Add a task to the queue."""
    from .db import Database

    async def _add():
        db = Database(db_path)
        await db.connect()
        task = await db.enqueue(prompt, priority=priority)
        click.echo(f"Enqueued task #{task.id}: {prompt[:60]}")
        await db.close()

    asyncio.run(_add())


@cli.command()
@click.option("--db", "db_path", default="cc_boss.db")
def status(db_path: str):
    """Show task queue status."""
    from .db import Database

    async def _status():
        db = Database(db_path)
        await db.connect()
        tasks = await db.list_tasks(limit=20)
        if not tasks:
            click.echo("No tasks.")
            return
        click.echo(f"{'ID':>4}  {'Status':<10}  {'Worker':>6}  {'Cost':>8}  Prompt")
        click.echo("-" * 80)
        for t in tasks:
            cost = f"${t.cost_usd:.3f}" if t.cost_usd else "-"
            worker = str(t.worker_id) if t.worker_id is not None else "-"
            click.echo(f"{t.id:>4}  {t.status:<10}  {worker:>6}  {cost:>8}  {t.prompt[:40]}")
        await db.close()

    asyncio.run(_status())


if __name__ == "__main__":
    cli()
