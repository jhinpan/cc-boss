"""Pydantic models for tasks, CC events, and run results."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    pending = "pending"
    planning = "planning"
    planned = "planned"
    running = "running"
    done = "done"
    failed = "failed"


class Task(BaseModel):
    id: int | None = None
    prompt: str
    status: TaskStatus = TaskStatus.pending
    priority: int = 0  # higher = more urgent
    worker_id: int | None = None
    plan: str | None = None
    result_summary: str | None = None
    error: str | None = None
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_s: float | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    finished_at: str | None = None


class CCEvent(BaseModel):
    """A single event from claude --output-format stream-json."""
    type: str  # system, assistant, tool_use, tool_result, result
    subtype: str | None = None
    content: str = ""
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    is_error: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def parse_line(cls, data: dict[str, Any]) -> CCEvent:
        """Parse a single stream-json line from CC."""
        evt_type = data.get("type", "unknown")
        content = ""
        tool_name = None
        tool_input = None
        is_error = False
        cost_usd = None
        tokens_in = None
        tokens_out = None
        subtype = data.get("subtype")

        if evt_type == "assistant":
            # Text content from assistant
            if isinstance(data.get("message"), dict):
                parts = data["message"].get("content", [])
                content = " ".join(
                    p.get("text", "") for p in parts if p.get("type") == "text"
                )
            elif isinstance(data.get("content_block"), dict):
                content = data["content_block"].get("text", "")

        elif evt_type == "content_block_delta":
            delta = data.get("delta", {})
            content = delta.get("text", "")

        elif evt_type == "tool_use":
            tool_name = data.get("name", data.get("tool_name", ""))
            tool_input = data.get("input", data.get("tool_input", {}))

        elif evt_type == "tool_result":
            content = str(data.get("content", data.get("output", "")))
            is_error = data.get("is_error", False)

        elif evt_type == "result":
            content = data.get("result", "")
            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens")
            tokens_out = usage.get("output_tokens")
            cost_usd = data.get("cost_usd") or data.get("cost")

        return cls(
            type=evt_type,
            subtype=subtype,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input,
            is_error=is_error,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            raw=data,
        )


class RunResult(BaseModel):
    """Aggregated result of a full CC run."""
    text: str = ""
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    errors: list[str] = Field(default_factory=list)
    events: list[CCEvent] = Field(default_factory=list)

    @classmethod
    def from_events(cls, events: list[CCEvent]) -> RunResult:
        texts = []
        errors = []
        cost = 0.0
        tin = 0
        tout = 0
        for e in events:
            if e.type == "assistant" and e.content:
                texts.append(e.content)
            if e.is_error and e.content:
                errors.append(e.content)
            if e.type == "result":
                cost = e.cost_usd or cost
                tin = e.tokens_in or tin
                tout = e.tokens_out or tout
        return cls(
            text="\n".join(texts),
            cost_usd=cost,
            tokens_in=tin,
            tokens_out=tout,
            errors=errors,
            events=events,
        )
