"""Reduce Copilot session events and OpenTelemetry into dashboard state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from perfrace.run.services.gateway import load_cost_models

IDLE_REQUEST_ID = "__assistant_idle__"
IDLE_REASON = "Agent is idle and waiting for Human input."


@dataclass(frozen=True)
class EventSnapshot:
    """Current engagement and usage state derived from persisted events."""

    needs_human: bool = False
    engagement_kind: str | None = None
    engagement_reason: str | None = None
    failed: bool = False
    error: str | None = None
    human_interactions: int = 0
    live_cost_usd: float | None = 0.0


def read_appended_jsonl(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    """Read complete records appended after ``offset``."""
    if not path.is_file():
        return [], 0
    size = path.stat().st_size
    if size < offset:
        offset = 0
    records: list[dict[str, Any]] = []
    new_offset = offset
    with path.open("rb") as handle:
        handle.seek(offset)
        while True:
            line_offset = handle.tell()
            line = handle.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                new_offset = line_offset
                break
            new_offset = handle.tell()
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path} offset {line_offset}") from exc
            if isinstance(value, dict):
                records.append(value)
    return records, new_offset


def _event_request_id(data: dict[str, Any]) -> str:
    return str(data.get("requestId") or data.get("interactionId") or "")


def _permission_reason(data: dict[str, Any]) -> str:
    request = data.get("permissionRequest")
    if not isinstance(request, dict):
        return "Tool permission"
    intention = request.get("intention")
    file_name = request.get("fileName")
    if intention and file_name:
        return f"{intention}: {file_name}"
    return str(intention or request.get("kind") or "Tool permission")


def _elicitation_reason(data: dict[str, Any]) -> str:
    for key in ("message", "prompt", "title", "question"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Review requested"


def _ask_user_reason(data: dict[str, Any]) -> str:
    arguments = data.get("arguments")
    if isinstance(arguments, dict):
        message = arguments.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return "Review requested"


class EventTracker:
    """Incrementally track one session's Copilot and OTel JSONL files."""

    def __init__(self, automatic_prompt: str):
        self.automatic_prompt = automatic_prompt.strip()
        self.event_offset = 0
        self.otel_offsets: dict[Path, int] = {}
        self.pending: dict[str, tuple[str, str]] = {}
        self.ask_user_calls: set[str] = set()
        self.failed = False
        self.error: str | None = None
        self.human_interactions = 0
        self.live_cost_usd = 0.0
        self.cost_available = True
        self.seen_spans: set[str] = set()

    def refresh(self, event_path: Path, otel_paths: list[Path]) -> EventSnapshot:
        events, self.event_offset = read_appended_jsonl(event_path, self.event_offset)
        for event in events:
            self._apply_event(event)
        for path in otel_paths:
            records, offset = read_appended_jsonl(path, self.otel_offsets.get(path, 0))
            self.otel_offsets[path] = offset
            self._apply_otel(records)
        kind = reason = None
        if self.pending:
            kind, reason = next(reversed(self.pending.values()))
        return EventSnapshot(
            needs_human=bool(self.pending),
            engagement_kind=kind,
            engagement_reason=reason,
            failed=self.failed,
            error=self.error,
            human_interactions=self.human_interactions,
            live_cost_usd=self.live_cost_usd if self.cost_available else None,
        )

    def _apply_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        data = event.get("data")
        data = data if isinstance(data, dict) else {}
        request_id = _event_request_id(data) or str(event.get("id") or "")
        if event_type == "elicitation.requested":
            self.pending[request_id] = ("review", _elicitation_reason(data))
        elif event_type == "permission.requested":
            self.pending[request_id] = ("permission", _permission_reason(data))
        elif event_type == "tool.execution_start" and data.get("toolName") == "ask_user":
            tool_call_id = str(data.get("toolCallId") or request_id)
            self.ask_user_calls.add(tool_call_id)
            self.pending[tool_call_id] = ("review", _ask_user_reason(data))
        elif event_type in {"elicitation.completed", "permission.completed"}:
            self.pending.pop(request_id, None)
        elif event_type == "tool.execution_complete":
            tool_call_id = str(data.get("toolCallId") or request_id)
            self.pending.pop(tool_call_id, None)
            if tool_call_id in self.ask_user_calls:
                self.ask_user_calls.remove(tool_call_id)
                if data.get("success") is True:
                    self.human_interactions += 1
        elif event_type == "session.error":
            self.pending.pop(IDLE_REQUEST_ID, None)
            self.failed = True
            raw_error = data.get("error") or data.get("message")
            self.error = str(raw_error or "Copilot session error")
        elif event_type in {"session.resume", "session.start"}:
            self.failed = False
            self.error = None
        elif event_type == "assistant.turn_start":
            self.pending.pop(IDLE_REQUEST_ID, None)
            self.failed = False
            self.error = None
        elif event_type == "assistant.turn_end":
            self.pending[IDLE_REQUEST_ID] = ("idle", IDLE_REASON)
        elif event_type == "user.message":
            self.pending.pop(IDLE_REQUEST_ID, None)
            content = data.get("content")
            if not isinstance(content, str) or content.strip() != self.automatic_prompt:
                self.human_interactions += 1

    def _apply_otel(self, records: list[dict[str, Any]]) -> None:
        cost_models = load_cost_models()
        for record in records:
            if record.get("type") != "span":
                continue
            attributes = record.get("attributes")
            if not isinstance(attributes, dict):
                continue
            if attributes.get("gen_ai.operation.name") != "chat":
                continue
            span_id = str(record.get("spanId") or "")
            if span_id and span_id in self.seen_spans:
                continue
            if span_id:
                self.seen_spans.add(span_id)
            model = attributes.get("gen_ai.response.model") or attributes.get(
                "gen_ai.request.model"
            )
            cost_model = cost_models.get(str(model))
            if cost_model is None:
                self.cost_available = False
                continue
            input_tokens = int(attributes.get("gen_ai.usage.input_tokens") or 0)
            output_tokens = int(attributes.get("gen_ai.usage.output_tokens") or 0)
            cached_tokens = int(attributes.get("gen_ai.usage.cache_read.input_tokens") or 0)
            uncached_tokens = max(input_tokens - cached_tokens, 0)
            self.live_cost_usd += (
                uncached_tokens * cost_model.input_cost_per_token
                + cached_tokens * cost_model.cached_input_cost_per_token
                + output_tokens * cost_model.output_cost_per_token
            )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read complete JSON objects and ignore a trailing partial line."""
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break
            raise ValueError(f"invalid JSONL at {path}:{index + 1}") from None
        if isinstance(value, dict):
            events.append(value)
    return events


def reduce_copilot_events(
    events: list[dict[str, Any]],
    *,
    automatic_prompt: str,
) -> EventSnapshot:
    """Reduce native Copilot events to the latest Human-engagement state."""
    pending: dict[str, tuple[str, str]] = {}
    ask_user_calls: set[str] = set()
    failed = False
    error: str | None = None
    interactions = 0
    normalized_prompt = automatic_prompt.strip()

    for event in events:
        event_type = event.get("type")
        data = event.get("data")
        data = data if isinstance(data, dict) else {}
        request_id = _event_request_id(data)

        if event_type == "elicitation.requested":
            pending[request_id] = ("review", _elicitation_reason(data))
        elif event_type == "permission.requested":
            pending[request_id] = ("permission", _permission_reason(data))
        elif event_type == "tool.execution_start" and data.get("toolName") == "ask_user":
            tool_call_id = str(data.get("toolCallId") or request_id)
            ask_user_calls.add(tool_call_id)
            pending[tool_call_id] = (
                "review",
                _ask_user_reason(data),
            )
        elif event_type in {"elicitation.completed", "permission.completed"}:
            pending.pop(request_id, None)
        elif event_type == "tool.execution_complete":
            tool_call_id = str(data.get("toolCallId") or request_id)
            pending.pop(tool_call_id, None)
            if tool_call_id in ask_user_calls:
                ask_user_calls.remove(tool_call_id)
                if data.get("success") is True:
                    interactions += 1
        elif event_type == "session.error":
            pending.pop(IDLE_REQUEST_ID, None)
            failed = True
            raw_error = data.get("error") or data.get("message")
            error = str(raw_error or "Copilot session error")
        elif event_type in {"session.resume", "session.start"}:
            failed = False
            error = None
        elif event_type == "assistant.turn_start":
            pending.pop(IDLE_REQUEST_ID, None)
            failed = False
            error = None
        elif event_type == "assistant.turn_end":
            pending[IDLE_REQUEST_ID] = ("idle", IDLE_REASON)
        elif event_type == "user.message":
            pending.pop(IDLE_REQUEST_ID, None)
            content = data.get("content")
            if not isinstance(content, str) or content.strip() != normalized_prompt:
                interactions += 1

    if pending:
        kind, reason = next(reversed(pending.values()))
        return EventSnapshot(
            needs_human=True,
            engagement_kind=kind,
            engagement_reason=reason,
            failed=failed,
            error=error,
            human_interactions=interactions,
        )
    return EventSnapshot(failed=failed, error=error, human_interactions=interactions)


def estimate_otel_cost_usd(records: list[dict[str, Any]]) -> float | None:
    """Estimate live cost from completed chat spans using configured rates."""
    cost_models = load_cost_models()
    total = 0.0
    found = False
    seen_spans: set[str] = set()

    for record in records:
        if record.get("type") != "span":
            continue
        attributes = record.get("attributes")
        if not isinstance(attributes, dict):
            continue
        if attributes.get("gen_ai.operation.name") != "chat":
            continue
        span_id = str(record.get("spanId") or "")
        if span_id and span_id in seen_spans:
            continue
        if span_id:
            seen_spans.add(span_id)
        model = attributes.get("gen_ai.response.model") or attributes.get("gen_ai.request.model")
        cost_model = cost_models.get(str(model))
        if cost_model is None:
            return None
        input_tokens = int(attributes.get("gen_ai.usage.input_tokens") or 0)
        output_tokens = int(attributes.get("gen_ai.usage.output_tokens") or 0)
        cached_tokens = int(attributes.get("gen_ai.usage.cache_read.input_tokens") or 0)
        uncached_tokens = max(input_tokens - cached_tokens, 0)
        total += (
            uncached_tokens * cost_model.input_cost_per_token
            + cached_tokens * cost_model.cached_input_cost_per_token
            + output_tokens * cost_model.output_cost_per_token
        )
        found = True

    return total if found else 0.0
