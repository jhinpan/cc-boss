"""Tests for CC event parsing and run result aggregation."""

import pytest

from cc_boss.models import CCEvent, RunResult


def test_parse_assistant_event():
    data = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Hello world"}]
        }
    }
    event = CCEvent.parse_line(data)
    assert event.type == "assistant"
    assert event.content == "Hello world"
    assert not event.is_error


def test_parse_tool_use_event():
    data = {
        "type": "tool_use",
        "name": "Read",
        "input": {"file_path": "/tmp/test.py"}
    }
    event = CCEvent.parse_line(data)
    assert event.type == "tool_use"
    assert event.tool_name == "Read"
    assert event.tool_input == {"file_path": "/tmp/test.py"}


def test_parse_tool_result_error():
    data = {
        "type": "tool_result",
        "content": "File not found",
        "is_error": True,
    }
    event = CCEvent.parse_line(data)
    assert event.type == "tool_result"
    assert event.is_error
    assert "not found" in event.content


def test_parse_result_event():
    data = {
        "type": "result",
        "result": "Task completed",
        "usage": {"input_tokens": 1000, "output_tokens": 500},
        "cost_usd": 0.05,
    }
    event = CCEvent.parse_line(data)
    assert event.type == "result"
    assert event.tokens_in == 1000
    assert event.tokens_out == 500
    assert event.cost_usd == 0.05


def test_run_result_from_events():
    events = [
        CCEvent.parse_line({"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 1"}]}}),
        CCEvent.parse_line({"type": "tool_result", "content": "Error!", "is_error": True}),
        CCEvent.parse_line({"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 2"}]}}),
        CCEvent.parse_line({"type": "result", "result": "done", "usage": {"input_tokens": 500, "output_tokens": 200}, "cost_usd": 0.02}),
    ]
    result = RunResult.from_events(events)
    assert "Step 1" in result.text
    assert "Step 2" in result.text
    assert len(result.errors) == 1
    assert result.cost_usd == 0.02
    assert result.tokens_in == 500
