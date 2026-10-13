"""Evolvable TerminusBoxBox review and candidate preparation."""

from __future__ import annotations

import copy
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harbor.agents.terminus_2.tmux_session import TmuxSession
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths

from boxbox.terminus_boxbox.kernel.interfaces import (
    FaultReport,
    ReviewResult,
    RuntimeTrap,
)
from boxbox.terminus_boxbox.kernel.lifecycle import (
    FAULT_LOG,
    REVIEW_USER,
    HARNESS_DIR,
    RUNTIME_STATE_DIR,
    prepare_runtime_state_dir,
)

if TYPE_CHECKING:
    from .agent import TerminusBoxBox, ReviewContextCapture, ReviewContextWindow

FEEDBACK_FILE = f"{RUNTIME_STATE_DIR}/review-feedback.txt"
TASK_CONTEXT_PREFIX = "Original target task:\n"
DEFAULT_QUERY_BYTES = 12_000
MAX_QUERY_BYTES = 24_000
DEFAULT_QUERY_LIMIT = 20
QUERY_FIELDS = {
    "message",
    "reasoning",
    "tool_calls",
    "observation",
    "metrics",
}
CONTEXT_VIEWS = {"epoch", "delta"}
REVIEW_CONTEXT_TOOL = {
    "type": "function",
    "function": {
        "name": "review_context",
        "description": (
            "Inspect Target trajectory evidence through compact event references. "
            "List event metadata, search raw evidence and return matching references, "
            "or read selected raw fields under a byte budget. Follow next/more to "
            "continue."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "search", "read"],
                },
                "view": {
                    "type": "string",
                    "enum": ["delta", "epoch"],
                },
                "after": {"type": "integer", "minimum": 0},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
                "seq": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "uniqueItems": True,
                },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": sorted(QUERY_FIELDS),
                    },
                    "uniqueItems": True,
                },
                "query": {"type": "string"},
                "regex": {"type": "boolean"},
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1024,
                    "maximum": MAX_QUERY_BYTES,
                },
            },
            "required": ["action", "view"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class ReviewContextSource:
    """One canonical trajectory and the cursor bounds exposed to a reviewer."""

    trajectory: Path
    index: Path
    accepted_after: int
    presented_after: int
    through: int


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_bytes(value: Any) -> int:
    return len(_compact_json(value).encode("utf-8"))


def _value_bytes(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return _json_bytes(value)


def _tool_names(step: dict[str, Any]) -> list[str]:
    names: list[str] = []
    tool_calls = step.get("tool_calls")
    if not isinstance(tool_calls, list):
        return names
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        name = tool_call.get("function_name")
        if not isinstance(name, str):
            function = tool_call.get("function")
            name = function.get("name") if isinstance(function, dict) else None
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _result_sizes(step: dict[str, Any]) -> list[int]:
    observation = step.get("observation")
    if not isinstance(observation, dict):
        return []
    results = observation.get("results")
    if not isinstance(results, list):
        return []
    sizes = []
    for result in results:
        if isinstance(result, dict) and "content" in result:
            result = result["content"]
        sizes.append(_value_bytes(result))
    return sizes


def build_context_index(
    source: Path,
    destination: Path,
    *,
    through_offset: int,
) -> int:
    """Build one minimal byte-addressable index for the canonical trajectory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        if through_offset:
            raise RuntimeError("Review trajectory journal is missing")
        destination.write_bytes(b"")
        return 0
    count = 0
    offset = 0
    with (
        source.open("rb") as input_stream,
        destination.open(
            "w",
            encoding="utf-8",
        ) as output_stream,
    ):
        while offset < through_offset:
            raw_line = input_stream.readline()
            if not raw_line or offset + len(raw_line) > through_offset:
                raise RuntimeError("Review trajectory snapshot ends inside a record")
            line_offset = offset
            offset += len(raw_line)
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid review context at byte {line_offset}") from error
            if not isinstance(record, dict):
                raise ValueError(f"Review context event at byte {line_offset} is not an object")
            step = record.get("step")
            step = step if isinstance(step, dict) else {}
            entry = {
                "seq": record.get("sequence"),
                "phase": record.get("phase"),
                "time": step.get("timestamp"),
                "kind": record.get("kind"),
                "source": step.get("source"),
                "tools": _tool_names(step),
                "result_bytes": _result_sizes(step),
                "offset": line_offset,
                "length": len(raw_line),
            }
            output_stream.write(f"{_compact_json(entry)}\n")
            count += 1
    if offset != through_offset:
        raise RuntimeError("Review trajectory snapshot offset is invalid")
    return count


def _load_context_index(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid review index line {line_number}") from error
            if not isinstance(entry, dict) or type(entry.get("seq")) is not int:
                raise ValueError(f"Invalid review index entry at line {line_number}")
            entries.append(entry)
    return entries


def _read_context_event(source: Path, entry: dict[str, Any]) -> dict[str, Any]:
    offset = entry.get("offset")
    length = entry.get("length")
    if type(offset) is not int or offset < 0 or type(length) is not int or length <= 0:
        raise ValueError("Review index contains an invalid byte range")
    with source.open("rb") as stream:
        stream.seek(offset)
        payload = stream.read(length)
    try:
        record = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Review event at byte {offset} is invalid") from error
    if not isinstance(record, dict):
        raise ValueError(f"Review event at byte {offset} is not an object")
    return record


def _project_context_event(
    record: dict[str, Any],
    entry: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    step = record.get("step")
    step = step if isinstance(step, dict) else {}
    event = dict(entry)
    for field in fields:
        if field == "reasoning":
            event[field] = step.get("reasoning_content")
        elif field == "metrics" and record.get("kind") == "phase_end":
            event[field] = record.get("final_metrics")
        else:
            event[field] = step.get(field)
    return event


def _truncate_context_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    marker = f"\n...[{len(encoded) - max_bytes} bytes omitted]...\n".encode()
    content_budget = max(0, max_bytes - len(marker))
    head_budget = content_budget // 2
    tail_budget = content_budget - head_budget
    head = encoded[:head_budget].decode("utf-8", errors="ignore")
    tail = encoded[-tail_budget:].decode("utf-8", errors="ignore") if tail_budget else ""
    return f"{head}{marker.decode()}{tail}"


def _truncate_context_strings(value: Any, max_string_bytes: int) -> Any:
    if isinstance(value, str):
        return _truncate_context_text(value, max_string_bytes)
    if isinstance(value, list):
        return [_truncate_context_strings(item, max_string_bytes) for item in value]
    if isinstance(value, dict):
        return {
            key: _truncate_context_strings(item, max_string_bytes) for key, item in value.items()
        }
    return value


def _fit_context_event(event: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    if _json_bytes(event) <= max_bytes:
        return event
    for string_budget in (4096, 2048, 1024, 512, 256, 128, 64, 0):
        candidate = _truncate_context_strings(event, string_budget)
        candidate["truncated"] = True
        if _json_bytes(candidate) <= max_bytes:
            return candidate
    return {
        "seq": event.get("seq"),
        "phase": event.get("phase"),
        "kind": event.get("kind"),
        "offset": event.get("offset"),
        "length": event.get("length"),
        "truncated": True,
    }


def _render_context_result(
    events: list[dict[str, Any]],
    next_cursor: int,
    more: bool,
) -> str:
    return _compact_json({"events": events, "next": next_cursor, "more": more})


def _bounded_context_page(
    candidates: list[tuple[int, dict[str, Any]]],
    *,
    after: int,
    limit: int,
    max_bytes: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    events: list[dict[str, Any]] = []
    next_cursor = after
    consumed = 0
    for seq, event in candidates:
        if len(events) >= limit:
            break
        remaining = (
            max_bytes - len(_render_context_result(events, next_cursor, True).encode("utf-8")) - 64
        )
        fitted = _fit_context_event(event, max(256, remaining))
        candidate_events = [*events, fitted]
        if len(_render_context_result(candidate_events, seq, True).encode("utf-8")) > max_bytes:
            break
        events = candidate_events
        next_cursor = seq
        consumed += 1
    return events, next_cursor, consumed < len(candidates)


def _validated_query_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    action = arguments.get("action")
    view = arguments.get("view")
    if action not in {"list", "search", "read"}:
        raise ValueError("action must be list, search, or read")
    if view not in CONTEXT_VIEWS:
        raise ValueError("view must be delta or epoch")
    after = arguments.get("after", 0)
    limit = arguments.get("limit", DEFAULT_QUERY_LIMIT)
    max_bytes = arguments.get("max_bytes", DEFAULT_QUERY_BYTES)
    fields = arguments.get("fields", ["message", "tool_calls", "observation"])
    sequences = arguments.get("seq", [])
    if type(after) is not int or after < 0:
        raise ValueError("after must be a non-negative integer")
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if type(max_bytes) is not int or not 1024 <= max_bytes <= MAX_QUERY_BYTES:
        raise ValueError(f"max_bytes must be between 1024 and {MAX_QUERY_BYTES}")
    if not isinstance(fields, list) or not fields:
        raise ValueError("fields must be a non-empty array")
    if any(not isinstance(field, str) or field not in QUERY_FIELDS for field in fields):
        raise ValueError("fields contains an unsupported value")
    if not isinstance(sequences, list) or any(
        type(sequence) is not int or sequence <= 0 for sequence in sequences
    ):
        raise ValueError("seq must contain positive integers")
    query = arguments.get("query")
    regex = arguments.get("regex", False)
    if action == "search" and (not isinstance(query, str) or not query):
        raise ValueError("search requires a non-empty query")
    if type(regex) is not bool:
        raise ValueError("regex must be a boolean")
    return {
        "action": action,
        "view": view,
        "after": after,
        "limit": limit,
        "max_bytes": max_bytes,
        "fields": tuple(fields),
        "sequences": tuple(sequences),
        "query": query,
        "regex": regex,
    }


def query_context(source: ReviewContextSource, arguments: dict[str, Any]) -> str:
    """Execute the reviewer-only context tool against immutable local artifacts."""
    if not isinstance(arguments, dict):
        raise ValueError("review_context arguments must be an object")
    options = _validated_query_arguments(arguments)
    entries = _load_context_index(source.index)
    view_after = source.accepted_after if options["view"] == "epoch" else source.presented_after
    lower_bound = max(view_after, options["after"])
    visible = [entry for entry in entries if view_after < entry["seq"] <= source.through]
    remaining = [entry for entry in visible if entry["seq"] > lower_bound]

    if options["action"] == "list":
        candidates = [(entry["seq"], entry) for entry in remaining]
    elif options["action"] == "read":
        if options["sequences"]:
            wanted = set(options["sequences"])
            selected = [entry for entry in visible if entry["seq"] in wanted]
            missing = sorted(wanted - {entry["seq"] for entry in selected})
            if missing:
                raise ValueError(f"Sequences not present in {options['view']}: {missing}")
        else:
            selected = remaining
        candidates = [
            (
                entry["seq"],
                _project_context_event(
                    _read_context_event(source.trajectory, entry),
                    entry,
                    options["fields"],
                ),
            )
            for entry in selected
        ]
    else:
        pattern = re.compile(options["query"], re.IGNORECASE) if options["regex"] else None
        matches: list[tuple[int, dict[str, Any]]] = []
        next_cursor = options["after"]
        consumed = 0
        for entry in remaining:
            if len(matches) >= options["limit"]:
                break
            record = _read_context_event(source.trajectory, entry)
            evidence = _compact_json(_project_context_event(record, entry, options["fields"]))
            matched = (
                bool(pattern.search(evidence))
                if pattern is not None
                else options["query"].casefold() in evidence.casefold()
            )
            if matched:
                candidate = [event for _, event in matches] + [entry]
                if (
                    len(
                        _render_context_result(
                            candidate,
                            entry["seq"],
                            True,
                        ).encode("utf-8")
                    )
                    > options["max_bytes"]
                ):
                    break
                matches.append((entry["seq"], entry))
            next_cursor = entry["seq"]
            consumed += 1
        return _render_context_result(
            [event for _, event in matches],
            next_cursor,
            consumed < len(remaining),
        )

    events, next_cursor, more = _bounded_context_page(
        candidates,
        after=options["after"],
        limit=options["limit"],
        max_bytes=options["max_bytes"],
    )
    return _render_context_result(events, next_cursor, more)


def handle_context_tool(
    source: ReviewContextSource | None,
    arguments: dict[str, Any],
) -> str:
    """Return a bounded result or a compact correction as a native tool result."""
    if source is None:
        return _compact_json({"error": "review context is not configured"})
    try:
        return query_context(source, arguments)
    except (OSError, ValueError, re.error) as error:
        return _compact_json({"error": str(error)})


def _format_context_window(window: ReviewContextWindow) -> str:
    """Format authoritative mechanical bounds for the incremental context."""
    if not window.record_count:
        return "- records: 0\n- phases present: none"
    phases = ", ".join(str(phase.phase) for phase in window.phases)
    phase_details = "\n".join(
        (
            f"  - phase {phase.phase}: {phase.step_count} steps, "
            f"{'complete' if phase.complete else 'incomplete'}"
        )
        for phase in window.phases
    )
    return (
        f"- sequences: {window.first_sequence} through {window.last_sequence}\n"
        f"- records: {window.record_count}\n"
        f"- phases present: {phases}\n"
        f"{phase_details}"
    )


def build_prompt(
    environment: BaseEnvironment,
    *,
    sequence: int,
    fault_report: FaultReport | None,
    feedback_enabled: bool,
    epoch_window: ReviewContextWindow,
    delta_window: ReviewContextWindow,
) -> str:
    """Build one continuing review instruction from runtime-owned resources."""
    if fault_report is None:
        problem = ""
    else:
        interval = (
            f"after {fault_report.last_reviewed_at} and through {fault_report.latest_event_at}"
            if fault_report.last_reviewed_at is not None
            else f"through {fault_report.latest_event_at}"
        )
        problem = f"""
## Current fault report
Read events in {FAULT_LOG} with timestamps {interval}. Determine how they affect
this review.
"""
    if feedback_enabled:
        feedback_state = "enabled"
    else:
        feedback_state = "unavailable for this transition"
    return f"""\
## Review transition {sequence}

## Session state
- target workspace: {environment.task_env_config.workdir}
- Target trajectory: canonical `review-trajectory.jsonl` via `review_context`
- trajectory views: `delta` since the previous judgment; `epoch` since the
  current harness was accepted
- harness repository: {HARNESS_DIR}
- Review feedback: {feedback_state}
{problem}

## Accepted-harness context window
{_format_context_window(epoch_window)}

## New context delta
{_format_context_window(delta_window)}

Read the new delta first. Consult the full accepted-harness context only when
the new evidence depends on an earlier unresolved pattern or conclusion.

Use the reviewer-only `review_context` tool to list the delta, search either
logical view, and read selected raw fields from the same canonical trajectory.
Every result is bounded and reports `next` and `more`; continue with that
`next` value as `after`. Search returns compact event positions, so use `read`
to inspect the relevant original evidence. Preserve useful historical
references as view plus sequence numbers.

Inspect the current runtime `HEAD` and status before editing. Read runtime
source only when the trajectory supports a concrete harness adaptation. The
target workspace is read-only. Treat a non-empty feedback handoff as a harness
adaptation: add it with `git add -f`, commit it in the clean successor, and do
not describe the decision as retention. Submit the unchanged current `HEAD`
only when the review provides no new Target-facing guidance or other useful
adaptation.
"""


async def prepare_artifacts(
    runtime: TerminusBoxBox,
    reviewer: TerminusBoxBox,
    environment: BaseEnvironment,
    *,
    feedback_enabled: bool,
) -> ReviewContextCapture:
    """Expose two logical views over one indexed canonical trajectory."""
    reviewer.logs_dir.mkdir(parents=True, exist_ok=True)
    capture = runtime.capture_review_context()
    trajectory = runtime.logs_dir / "review-trajectory.jsonl"
    context_index = reviewer.logs_dir / "review-trajectory.index.jsonl"
    build_context_index(
        trajectory,
        context_index,
        through_offset=capture.through_offset,
    )
    reviewer._review_context_source = ReviewContextSource(
        trajectory=trajectory,
        index=context_index,
        accepted_after=capture.accepted_sequence,
        presented_after=capture.presented_sequence,
        through=capture.through_sequence,
    )
    await prepare_runtime_state_dir(environment)
    if feedback_enabled:
        reset_feedback = await environment.exec(
            (f": > {shlex.quote(FEEDBACK_FILE)} && chmod 644 {shlex.quote(FEEDBACK_FILE)}"),
            cwd=HARNESS_DIR,
            timeout_sec=30,
            user=REVIEW_USER,
        )
        if reset_feedback.return_code != 0:
            raise RuntimeError(
                reset_feedback.stdout or reset_feedback.stderr or "failed to reset Agent feedback"
            )
    return capture


async def prepare_reviewer(
    runtime: TerminusBoxBox,
    reviewer: TerminusBoxBox,
    environment: BaseEnvironment,
    *,
    sequence: int,
) -> None:
    """Configure a Kernel-created reviewer with a fresh unprivileged terminal."""
    reviewer.logs_dir.mkdir(parents=True, exist_ok=True)
    reviewer.configure_review_phase(
        policy=runtime.boxbox_policy(),
    )
    task_message = {
        "role": "user",
        "content": f"{TASK_CONTEXT_PREFIX}{runtime.task_instruction}",
    }
    if runtime.review_chat_state is not None:
        chat_state = copy.deepcopy(runtime.review_chat_state)
        messages = chat_state.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RuntimeError("Persisted review Chat has no messages")
        messages[0] = {"role": "system", "content": reviewer.system_prompt()}
        messages[1:] = [
            message
            for message in messages[1:]
            if not (
                message.get("role") == "user"
                and isinstance(message.get("content"), str)
                and message["content"].startswith(TASK_CONTEXT_PREFIX)
            )
        ]
        messages.insert(1, task_message)
        reviewer.set_chat_state_for_next_run(chat_state)
    else:
        reviewer.set_chat_state_for_next_run(
            {
                "schema_version": 1,
                "messages": [
                    {"role": "system", "content": reviewer.system_prompt()},
                    task_message,
                ],
            }
        )
    reviewer._session = TmuxSession(
        session_name=f"runtime-review-{sequence:04d}",
        environment=environment,
        logging_path=EnvironmentPaths.agent_dir / f"runtime-review-{sequence:04d}.pane",
        local_asciinema_recording_path=None,
        remote_asciinema_recording_path=None,
        pane_width=reviewer._tmux_pane_width,
        pane_height=reviewer._tmux_pane_height,
        extra_env=reviewer._extra_env,
        user=REVIEW_USER,
    )
    await reviewer._session.start()


async def run(
    runtime: TerminusBoxBox,
    environment: BaseEnvironment,
    context: AgentContext,
    *,
    sequence: int,
    reviewer: TerminusBoxBox,
    fault_report: FaultReport | None,
    feedback_enabled: bool,
) -> ReviewResult:
    """Run one continuing review Chat under the transition timeout."""
    capture = await prepare_artifacts(
        runtime,
        reviewer,
        environment,
        feedback_enabled=feedback_enabled,
    )
    await prepare_reviewer(runtime, reviewer, environment, sequence=sequence)
    prompt = build_prompt(
        environment,
        sequence=sequence,
        fault_report=fault_report,
        feedback_enabled=feedback_enabled,
        epoch_window=capture.epoch,
        delta_window=capture.delta,
    )
    reviewer.set_task_instruction(prompt)
    try:
        trap = await reviewer.run_until_trap(prompt, environment, context)
        if trap != RuntimeTrap.COMPLETE:
            raise RuntimeError("Review ended before confirmed completion")
        feedback_ready = False
        if feedback_enabled:
            feedback_check = await environment.exec(
                (
                    f"if [ ! -s {shlex.quote(FEEDBACK_FILE)} ] || "
                    f"! grep -q '[^[:space:]]' {shlex.quote(FEEDBACK_FILE)}; then "
                    "printf 'empty\\n'; "
                    f'elif [ "$(wc -c < {shlex.quote(FEEDBACK_FILE)})" -le 65536 ]; then '
                    "printf 'present\\n'; "
                    "else printf 'oversize\\n'; fi"
                ),
                cwd=HARNESS_DIR,
                timeout_sec=30,
                user=REVIEW_USER,
            )
            if feedback_check.return_code != 0:
                raise RuntimeError(
                    feedback_check.stdout
                    or feedback_check.stderr
                    or "failed to inspect Agent feedback"
                )
            feedback_status = feedback_check.stdout.strip()
            if feedback_status == "present":
                feedback_ready = True
                await environment.download_file(
                    source_path=FEEDBACK_FILE,
                    target_path=reviewer.logs_dir / "review-feedback.txt",
                )
            elif feedback_status != "empty":
                raise RuntimeError("Review feedback exceeds 65536 bytes")
        runtime.mark_review_context_presented(
            capture.through_sequence,
            capture.through_offset,
        )
        if feedback_ready:
            runtime.mark_review_feedback_ready()
        return ReviewResult(
            context_through_sequence=capture.through_sequence,
            context_through_offset=capture.through_offset,
        )
    finally:
        if reviewer._chat is not None:
            runtime.review_chat_state = reviewer._chat.dump_state()
        if reviewer._session is not None:
            await reviewer._session.stop()
