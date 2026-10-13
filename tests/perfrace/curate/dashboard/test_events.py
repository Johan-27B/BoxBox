from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfrace.curate.dashboard.events import (
    EventTracker,
    estimate_otel_cost_usd,
    reduce_copilot_events,
)


def test_reduce_events_tracks_review_and_permission_completion() -> None:
    events = [
        {"type": "user.message", "data": {"content": "automatic"}},
        {"type": "user.message", "data": {"content": "human question"}},
        {
            "type": "elicitation.requested",
            "data": {"requestId": "review-1", "message": "Approve Realism?"},
        },
        {"type": "elicitation.completed", "data": {"requestId": "review-1"}},
        {
            "type": "permission.requested",
            "data": {
                "requestId": "permission-1",
                "permissionRequest": {
                    "kind": "write",
                    "intention": "Update file",
                    "fileName": "/tmp/task.toml",
                },
            },
        },
    ]

    snapshot = reduce_copilot_events(events, automatic_prompt="automatic")

    assert snapshot.needs_human is True
    assert snapshot.engagement_kind == "permission"
    assert snapshot.engagement_reason == "Update file: /tmp/task.toml"
    assert snapshot.human_interactions == 1


def test_reduce_events_treats_ask_user_tool_as_review_request() -> None:
    events = [
        {
            "type": "tool.execution_start",
            "data": {
                "toolCallId": "ask-1",
                "toolName": "ask_user",
                "arguments": {"message": "请审核 Realism。"},
            },
        }
    ]

    waiting = reduce_copilot_events(events, automatic_prompt="")
    completed = reduce_copilot_events(
        [
            *events,
            {
                "type": "tool.execution_complete",
                "data": {"toolCallId": "ask-1", "success": True},
            },
        ],
        automatic_prompt="",
    )

    assert waiting.needs_human is True
    assert waiting.engagement_kind == "review"
    assert waiting.engagement_reason == "请审核 Realism。"
    assert completed.needs_human is False


def test_reduce_events_counts_completed_ask_user_response() -> None:
    snapshot = reduce_copilot_events(
        [
            {
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "ask-1",
                    "toolName": "ask_user",
                    "arguments": {"message": "Approve Realism?"},
                },
            },
            {
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "ask-1",
                    "success": True,
                    "result": {"content": "Approve"},
                },
            },
        ],
        automatic_prompt="",
    )

    assert snapshot.human_interactions == 1


def test_reduce_events_clears_engagement_and_surfaces_errors() -> None:
    events = [
        {
            "type": "permission.requested",
            "data": {"requestId": "permission-1"},
        },
        {
            "type": "permission.completed",
            "data": {"requestId": "permission-1"},
        },
        {"type": "session.error", "data": {"error": "provider failed"}},
    ]

    snapshot = reduce_copilot_events(events, automatic_prompt="")

    assert snapshot.needs_human is False
    assert snapshot.failed is True
    assert snapshot.error == "provider failed"


def test_reduce_events_marks_only_the_final_turn_end_as_idle() -> None:
    idle = reduce_copilot_events(
        [
            {"type": "assistant.turn_start", "data": {}},
            {"type": "assistant.message", "data": {"content": "Done."}},
            {"type": "assistant.turn_end", "data": {}},
        ],
        automatic_prompt="",
    )
    continued = reduce_copilot_events(
        [
            {"type": "assistant.turn_end", "data": {}},
            {"type": "assistant.turn_start", "data": {}},
        ],
        automatic_prompt="",
    )
    resumed = reduce_copilot_events(
        [
            {"type": "assistant.turn_end", "data": {}},
            {"type": "session.resume", "data": {}},
        ],
        automatic_prompt="",
    )

    assert idle.needs_human is True
    assert idle.engagement_kind == "idle"
    assert idle.engagement_reason == "Agent is idle and waiting for Human input."
    assert continued.needs_human is False
    assert resumed.needs_human is True


def test_otel_cost_uses_chat_spans_without_double_counting_parent_span() -> None:
    records = [
        {
            "type": "span",
            "spanId": "chat-1",
            "name": "chat gpt-5.6-sol",
            "attributes": {
                "gen_ai.operation.name": "chat",
                "gen_ai.response.model": "gpt-5.6-sol",
                "gen_ai.usage.input_tokens": 100,
                "gen_ai.usage.output_tokens": 10,
                "gen_ai.usage.cache_read.input_tokens": 20,
                "gen_ai.usage.cache_write.input_tokens": 30,
            },
        },
        {
            "type": "span",
            "spanId": "agent-1",
            "name": "invoke_agent",
            "attributes": {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.response.model": "gpt-5.6-sol",
                "gen_ai.usage.input_tokens": 100,
                "gen_ai.usage.output_tokens": 10,
            },
        },
    ]

    assert estimate_otel_cost_usd(records) == pytest.approx(0.00071)


def test_event_tracker_reads_only_appended_records(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    otel_path = tmp_path / "otel.jsonl"
    tracker = EventTracker("automatic")
    events_path.write_text(
        json.dumps({"type": "user.message", "data": {"content": "automatic"}})
        + "\n"
        + json.dumps({"type": "user.message", "data": {"content": "human"}})
        + "\n"
    )
    otel_path.write_text(
        json.dumps(
            {
                "type": "span",
                "spanId": "chat-1",
                "attributes": {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.response.model": "gpt-5.6-sol",
                    "gen_ai.usage.input_tokens": 100,
                    "gen_ai.usage.output_tokens": 10,
                    "gen_ai.usage.cache_read.input_tokens": 20,
                },
            }
        )
        + "\n"
    )

    first = tracker.refresh(events_path, [otel_path])
    second = tracker.refresh(events_path, [otel_path])

    assert first.human_interactions == second.human_interactions == 1
    assert first.live_cost_usd == second.live_cost_usd == pytest.approx(0.00071)


def test_event_tracker_counts_appended_ask_user_response_once(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    tracker = EventTracker("automatic")
    events_path.write_text(
        json.dumps(
            {
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "ask-1",
                    "toolName": "ask_user",
                    "arguments": {"message": "Approve Integrity?"},
                },
            }
        )
        + "\n"
    )

    waiting = tracker.refresh(events_path, [])
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "tool.execution_complete",
                    "data": {"toolCallId": "ask-1", "success": True},
                }
            )
            + "\n"
        )
    completed = tracker.refresh(events_path, [])
    repeated = tracker.refresh(events_path, [])

    assert waiting.human_interactions == 0
    assert completed.human_interactions == repeated.human_interactions == 1


def test_event_tracker_clears_idle_when_a_new_turn_starts(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    tracker = EventTracker("automatic")
    events_path.write_text(
        json.dumps({"type": "assistant.turn_end", "data": {}}) + "\n",
        encoding="utf-8",
    )

    idle = tracker.refresh(events_path, [])
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "assistant.turn_start", "data": {}}) + "\n")
    running = tracker.refresh(events_path, [])

    assert idle.needs_human is True
    assert idle.engagement_kind == "idle"
    assert running.needs_human is False
