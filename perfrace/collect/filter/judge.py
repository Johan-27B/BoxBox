"""Endpoint-backed structured Filter judgments."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from perfrace.run.services.gateway import TokenUsage, estimate_cost_usd

from ._constants import PROMPT_PATH
from .models import ModelJudgment

from perfrace.settings import endpoint, configured_model


async def iter_judgments(
    snapshots: list[dict[str, Any]],
    *,
    model: str,
    reasoning_effort: str,
    concurrency: int,
    timeout_seconds: int,
    retries: int,
    max_output_tokens: int,
    log_path: Path,
) -> AsyncIterator[dict[str, Any]]:
    """Yield normalized model outcomes as concurrent judgments complete."""
    model = configured_model("filter", model)
    instructions = PROMPT_PATH.read_text(encoding="utf-8")
    semaphore = asyncio.Semaphore(concurrency)

    async def judge_one(
        client: AsyncOpenAI,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = snapshot["candidate"]["repo_url"]
        last_error: Exception | None = None
        async with semaphore:
            for attempt in range(1, retries + 2):
                try:
                    response = await asyncio.wait_for(
                        client.responses.parse(
                            model=model,
                            reasoning={"effort": reasoning_effort},
                            instructions=instructions,
                            input=json.dumps(
                                snapshot,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            text_format=ModelJudgment,
                            max_output_tokens=max_output_tokens,
                            store=False,
                            timeout=timeout_seconds,
                        ),
                        timeout=timeout_seconds,
                    )
                    judgment = response.output_parsed
                    if not isinstance(judgment, ModelJudgment):
                        raise ValueError("model response did not contain a judgment")
                    usage_payload = (
                        response.usage.model_dump() if response.usage is not None else {}
                    )
                    usage = TokenUsage()
                    usage.add(model, usage_payload)
                    return {
                        "repo_url": repo_url,
                        "status": "JUDGED",
                        "snapshot_sha256": snapshot["snapshot_sha256"],
                        "judgment": judgment.model_dump(mode="json"),
                        "model": model,
                        "reasoning_effort": reasoning_effort,
                        "attempts": attempt,
                        "usage": usage.to_json_dict(),
                        "cost_usd": estimate_cost_usd(model, usage),
                    }
                except (
                    asyncio.TimeoutError,
                    OpenAIError,
                    TimeoutError,
                    ValidationError,
                    ValueError,
                ) as exc:
                    last_error = exc
            assert last_error is not None
            return {
                "repo_url": repo_url,
                "status": "ERROR",
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "error_type": type(last_error).__name__,
                "error": str(last_error),
                "model": model,
                "reasoning_effort": reasoning_effort,
                "attempts": retries + 1,
                "usage": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "requests": retries + 1,
                    "models": [model],
                },
                "cost_usd": None,
            }

    connection = endpoint()
    async with AsyncOpenAI(
        api_key=connection["api_key"],
        base_url=connection["base_url"],
        timeout=timeout_seconds,
    ) as client:
        tasks = [asyncio.create_task(judge_one(client, snapshot)) for snapshot in snapshots]
        for task in asyncio.as_completed(tasks):
            yield await task


def judgment_schema() -> dict[str, Any]:
    """Return the strict JSON schema for model output."""
    return ModelJudgment.model_json_schema()
