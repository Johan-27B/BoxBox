import json
from pathlib import Path

from perfrace.evolution.paths import HarnessEvolutionPaths
from perfrace.evolution.usage import build_usage_report, render_usage_markdown
from perfrace.run.types import RunSummary


def test_build_usage_report_accounts_for_all_observed_requests(
    tmp_path: Path,
) -> None:
    paths = HarnessEvolutionPaths(tmp_path, "demo")
    run_dir = paths.jobs / "train-i1-h0" / "perfrace"
    run_dir.mkdir(parents=True)
    trial_name = "task-a__candidate"
    summary = RunSummary(
        job_name="train-i1-h0",
        enable_cache=True,
        used_api_gateway=True,
        trial_count=2,
        tasks=[
            {
                "task_name": "perfrace/task-a",
                "baseline": None,
                "candidates": [
                    {
                        "trial_name": trial_name,
                        "agent": "offline-harness",
                        "trial_uri": (paths.jobs / "train-i1-h0" / trial_name).as_uri(),
                        "artifact": "candidate.json",
                        "reward": 1.0,
                    }
                ],
            }
        ],
    )
    (run_dir / "run.json").write_text(summary.model_dump_json(), encoding="utf-8")
    result_dir = paths.jobs / "train-i1-h0" / trial_name
    result_dir.mkdir(parents=True)
    result_dir.joinpath("result.json").write_text(
        json.dumps(
            {
                "step_results": [
                    {
                        "agent_result": {
                            "metadata": {
                                "api_request_times_msec": [1000.0, 3000.0],
                            }
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    token_dir = paths.root / "gateway" / "token-proxy"
    token_dir.mkdir(parents=True)
    target_session = f"{trial_name}__agent"
    target_records = [
        {
            "session_id": target_session,
            "model": "test-model",
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {
                    "cached_tokens": 40,
                    "cache_write_tokens": 10,
                },
                "output_tokens": 20,
                "output_tokens_details": {"reasoning_tokens": 5},
            },
        },
        {
            "session_id": target_session,
            "model": "test-model",
            "usage": {
                "input_tokens": 50,
                "input_tokens_details": {"cached_tokens": 25},
                "output_tokens": 10,
            },
        },
    ]
    token_dir.joinpath(f"{target_session}.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in target_records),
        encoding="utf-8",
    )
    meta_session = "demo-overview-i1-h0"
    token_dir.joinpath(f"{meta_session}.jsonl").write_text(
        json.dumps(
            {
                "session_id": meta_session,
                "model": "test-model",
                "usage": {"input_tokens": 30, "output_tokens": 4},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    failed_meta_session = "demo-evolve-i1-h0-retry"
    token_dir.joinpath("token-proxy-requests.log").write_text(
        "\n".join(
            [
                f"Forwarding token proxy request: session={target_session} "
                "model=gpt-5.6-luna path=v1/responses",
                f"Forwarding token proxy request: session={target_session} "
                "model=gpt-5.6-luna path=v1/responses",
                f"Forwarding token proxy request: session={target_session} "
                "model=gpt-5.6-luna path=v1/responses",
                f"Upstream LLM gateway returned HTTP error: session={target_session} "
                "status=500 path=v1/responses",
                f"Forwarding token proxy request: session={failed_meta_session} "
                "model=gpt-5.6-luna path=v1/responses",
                f"Upstream LLM gateway returned HTTP error: session={failed_meta_session} "
                "status=500 path=v1/responses",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    nginx_log = tmp_path / "nginx.log"
    nginx_log.write_text(
        f"{target_session} 127.0.0.1:4181 200\n{meta_session} 127.0.0.1:4177 200\n",
        encoding="utf-8",
    )

    report = build_usage_report(
        paths,
        experiment_name="demo",
        completed_iterations=1,
        nginx_log=nginx_log,
    )

    sessions = {session["session_id"]: session for session in report["sessions"]}
    target = sessions[target_session]
    assert target["phase"] == "target"
    assert target["iteration"] == 1
    assert target["generation"] == 0
    assert target["usage_records"] == 2
    assert target["forwarded_requests"] == 3
    assert target["http_errors"] == 1
    assert target["missing_usage_records"] == 1
    assert target["cached_input_tokens"] == 65
    assert target["cache_write_tokens"] == 10
    assert target["reasoning_tokens"] == 5
    assert target["endpoint"] == "127.0.0.1:4181"
    assert target["api_delay"] == {
        "samples": 2,
        "mean_seconds": 2.0,
        "median_seconds": 2.0,
        "p95_seconds": 2.9,
    }
    assert sessions[meta_session]["phase"] == "overview"
    assert sessions[failed_meta_session]["phase"] == "evolve"
    assert sessions[failed_meta_session]["usage_records"] == 0
    assert sessions[failed_meta_session]["missing_usage_records"] == 1
    assert report["by_iteration"]["1"]["usage_records"] == 3
    assert report["by_endpoint"]["127.0.0.1:4181"]["usage_records"] == 2
    assert report["total"]["usage_records"] == 3
    assert report["total"]["missing_usage_records"] == 2
    assert report["api_delay_by_endpoint"]["127.0.0.1:4181"] == {
        "samples": 2,
        "mean_seconds": 2.0,
        "median_seconds": 2.0,
        "p95_seconds": 2.9,
    }
    assert "$" in render_usage_markdown(report)
