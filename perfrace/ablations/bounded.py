"""Bounded review without changing the shared harness source or core kernel."""

from __future__ import annotations

import copy
import json
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any

from boxbox.terminus_boxbox.kernel.lifecycle import Kernel


class EditableSurface(str, Enum):
    TARGET_GUIDANCE = "target_guidance"
    TOOLS_OBSERVABILITY = "tools_observability"
    CONTEXT_MEMORY = "context_memory"
    RUNTIME_CONTROL = "runtime_control"
    REVIEW_POLICY = "review_policy"


BOUNDED_POLICY = """\
Before editing the harness, call select_editable_surface once to declare one
failure mechanism and one conceptual surface: target_guidance,
tools_observability, context_memory, runtime_control, or review_policy.
All changes in this review must address that single mechanism within that
surface. Multiple files are allowed when required by the same change; do not
bundle unrelated improvements. Keeping the harness unchanged requires no
declaration. A changed harness without a declaration is rejected.
"""

SELECT_SURFACE_TOOL = {
    "type": "function",
    "function": {
        "name": "select_editable_surface",
        "description": (
            "Declare one harness surface and the observed failure mechanism "
            "before editing. The selection cannot change during this review."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "surface": {"type": "string", "enum": [s.value for s in EditableSurface]},
                "failure_mechanism": {"type": "string", "minLength": 1, "maxLength": 4096},
            },
            "required": ["surface", "failure_mechanism"],
            "additionalProperties": False,
        },
    },
}


class BoundedReview:
    """Add a reviewer-only declaration to any loaded TerminusBoxBox revision."""

    _scope_decision: dict[str, str] | None = None

    def configure_review_phase(self, *, policy: str) -> None:
        self._scope_decision = None
        super().configure_review_phase(policy=f"{policy}\n\n{BOUNDED_POLICY}")

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        tools = super()._get_tool_definitions()
        if self._review_phase:
            tools.append(copy.deepcopy(SELECT_SURFACE_TOOL))
        return tools

    def _parse_tool_calls(self, tool_calls):
        declarations = [
            call
            for call in tool_calls
            if call.get("function", {}).get("name") == "select_editable_surface"
        ]
        if not declarations or not self._review_phase:
            return super()._parse_tool_calls(tool_calls)

        # Reject the entire batch: a declaration must precede, not accompany,
        # commands that edit the harness.
        warning = ""
        observation = None
        if len(tool_calls) != 1:
            warning = "Call select_editable_surface alone before issuing other tools."
        elif self._scope_decision is not None:
            warning = "The editable surface has already been selected for this review."
        else:
            try:
                arguments = declarations[0]["function"].get("arguments", "{}")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise TypeError("Expected an object.")
                surface = EditableSurface(arguments.get("surface"))
                mechanism = arguments.get("failure_mechanism")
                if (
                    not isinstance(mechanism, str)
                    or not mechanism.strip()
                    or len(mechanism) > 4096
                ):
                    raise ValueError(
                        "Provide a non-empty failure mechanism, up to 4096 characters."
                    )
                self._scope_decision = {
                    "surface": surface.value,
                    "failure_mechanism": mechanism.strip(),
                }
                observation = json.dumps({"status": "selected", **self._scope_decision})
            except (ValueError, TypeError) as error:
                warning = str(error)
        # Same parser result contract as H0; no command or lifecycle trap.
        return [], None, f"WARNINGS: {warning}" if warning else "", "", "", None, observation


class BoundedKernel(Kernel):
    """Reuse transitions and recovery; require and record bounded declarations."""

    _bounded_reviewer = None

    def _create_runtime(self, runtime_class, *, logs_dir=None):
        if not issubclass(runtime_class, BoundedReview):
            runtime_class = type(
                f"Bounded{runtime_class.__name__}", (BoundedReview, runtime_class), {}
            )
        return super()._create_runtime(runtime_class, logs_dir=logs_dir)

    def _create_reviewer(self, runtime, transition_dir):
        self._bounded_reviewer = super()._create_reviewer(runtime, transition_dir)
        return self._bounded_reviewer

    async def _read_candidate_commit(self, environment):
        commit = await super()._read_candidate_commit(environment)
        if commit != self.active_commit and self._decision() is None:
            raise RuntimeError(
                "Bounded harness revision requires an editable-surface declaration "
                "and failure mechanism"
            )
        return commit

    def _decision(self) -> dict[str, str] | None:
        return getattr(self._bounded_reviewer, "_scope_decision", None)

    def _write_transition(self, transition_dir: Path, **kwargs):
        super()._write_transition(transition_dir, **kwargs)
        decision = self._decision()
        report = {
            "mode": "bounded",
            "declaration": decision,
            "diff": None,
            "audit": "no_candidate_diff",
        }
        repository = transition_dir / "candidate-repository"
        candidate = kwargs["candidate_commit"]
        previous = kwargs["previous_commit"]
        if repository.is_dir() and candidate is not None and candidate != previous:
            patch = subprocess.run(
                ["git", "-C", str(repository), "diff", "--binary", previous, candidate],
                capture_output=True,
                check=True,
            )
            (transition_dir / "harness-diff.patch").write_bytes(patch.stdout)
            paths = self._git_text(
                repository, "diff", "--name-only", previous, candidate
            ).splitlines()
            report["diff"] = {"path": "harness-diff.patch", "files": paths}
            report["audit"] = audit_paths(decision, paths)
        path = transition_dir / "transition.json"
        payload = json.loads(path.read_text())
        payload["review_scope"] = report
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def audit_paths(decision: dict[str, str] | None, paths: list[str]) -> str:
    """Flag clear scope mismatches; shared Python source needs semantic review."""
    if decision is None:
        return "missing_declaration"
    policy = ("prompt-templates/review.txt", "skills/self_review/")
    guidance = (
        "prompt-templates/task.txt",
        "prompt-templates/self-review.txt",
        ".runtime/review-feedback.txt",
    )

    def belongs(path, prefixes):
        return any(
            path.startswith(prefix) if prefix.endswith("/") else path == prefix
            for prefix in prefixes
        )

    selected = decision["surface"]
    if selected in {EditableSurface.REVIEW_POLICY, EditableSurface.TARGET_GUIDANCE}:
        allowed = policy if selected == EditableSurface.REVIEW_POLICY else guidance
        return "path_consistent" if all(belongs(p, allowed) for p in paths) else "cross_surface"
    if any(belongs(p, policy + guidance) for p in paths):
        return "cross_surface"
    return "semantic_review_required"
