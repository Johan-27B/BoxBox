from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path

from perfrace.collect.filter import judge
from perfrace.collect.filter.models import ModelJudgment


def _judgment() -> ModelJudgment:
    return ModelJudgment.model_validate(
        {
            "gates": {
                "accessible": {"passed": True, "evidence": ["LICENSE"]},
                "reproducibility": {
                    "passed": True,
                    "evidence": ["package.json"],
                },
                "evaluation_potential": {
                    "passed": True,
                    "evidence": ["src/cli.ts"],
                },
                "resource_feasibility": {
                    "passed": True,
                    "evidence": ["Linux CPU-only"],
                    "linux_x86_64_runnable": True,
                    "special_hardware_required": False,
                },
            },
            "reason": "Pass.",
            "optimization_profile": {
                "computation": "Batch workflow compilation",
                "potential": "high",
                "performance_hint": "Repeated parsing and validation scale with inputs.",
            },
            "preliminary_process": {
                "name": "CLI",
                "workload_carrier": "portable_artifact",
                "setup_commands": ["npm install"],
                "build_commands": ["npm run build"],
                "smoke_command": "npm run cli -- input.json",
                "input": "JSON input",
                "output": "JSON output",
                "metric": "Wall-clock time",
                "correctness": "Output equality",
                "external_services": [],
            },
        }
    )


def test_iter_judgments_returns_structured_outcome(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Usage:
        def model_dump(self):
            return {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            }

    class Response:
        output_parsed = _judgment()
        usage = Usage()

    class Responses:
        async def parse(self, **_kwargs):
            return Response()

    class Client:
        responses = Responses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    @contextmanager
    def fake_proxy(_path):
        yield "http://127.0.0.1:4000/v1"

    monkeypatch.setattr(judge, "AsyncOpenAI", lambda **_kwargs: Client())
    snapshot = {
        "repo_url": "https://github.com/owner/project",
        "candidate": {"repo_url": "https://github.com/owner/project"},
        "snapshot_sha256": "a" * 64,
    }

    async def collect():
        return [
            result
            async for result in judge.iter_judgments(
                [snapshot],
                model="gpt-5.6-luna",
                reasoning_effort="high",
                concurrency=20,
                timeout_seconds=180,
                retries=1,
                max_output_tokens=8000,
                log_path=tmp_path / "proxy.log",
            )
        ]

    results = asyncio.run(collect())

    assert results[0]["status"] == "JUDGED"
    assert results[0]["usage"]["total_tokens"] == 120
