"""Recompute paper metrics from released numeric records, without model calls."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def load_records(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def check_manifest(root: Path) -> None:
    """Verify every declared file without executing any archived harness."""
    manifest = load(root / "manifest.json")
    for relative, expected in manifest["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"Manifest path escapes artifact directory: {relative}")
        content = path.read_bytes()
        if len(content) != expected["bytes"]:
            raise ValueError(f"File size mismatch: {relative}")
        if hashlib.sha256(content).hexdigest() != expected["sha256"]:
            raise ValueError(f"Checksum mismatch: {relative}")


def candidate_speedup(run: dict, event: dict) -> float:
    value = event["value"]
    if event["verdict"] != "ACCEPTED" or value is None:
        return 0.0
    if not math.isfinite(value) or value <= 0:
        return 0.0
    baseline = run["baseline_value"]
    if not math.isfinite(baseline) or baseline <= 0:
        raise ValueError("A baseline must be positive and finite")
    if run["direction"] == "minimize":
        return baseline / value
    if run["direction"] == "maximize":
        return value / baseline
    raise ValueError(f"Unknown metric direction: {run['direction']}")


def score_at(run: dict, seconds: float) -> float:
    return max(
        [1.0]
        + [
            candidate_speedup(run, event)
            for event in run["evaluations"]
            if event["analysis_seconds"] <= seconds
        ]
    )


def aggregate(records: list[dict]) -> tuple[dict, list[dict]]:
    return aggregate_scores([{**r, "score": score_at(r, r["budget_seconds"])} for r in records])


def aggregate_scores(records: list[dict]) -> tuple[dict, list[dict]]:
    """GM across repeats, HM across tasks, mean of paired task efficiency."""
    grouped = defaultdict(list)
    identities = set()
    for run in records:
        if run["run_id"] in identities:
            raise ValueError(f"Duplicate run: {run['run_id']}")
        identities.add(run["run_id"])
        grouped[(run["method"], run["task_id"])].append(run)
    rows = []
    for (method, task), runs in sorted(grouped.items()):
        scores = [r["score"] for r in runs]
        costs = [r["final_cost_usd"] for r in runs]
        if any(not math.isfinite(s) or s <= 0 for s in scores):
            raise ValueError(f"Score is missing or nonpositive: {method}/{task}")
        if any(not math.isfinite(c) or c <= 0 for c in costs):
            raise ValueError(f"Cost is missing or nonpositive: {method}/{task}")
        score = statistics.geometric_mean(scores)
        cost = statistics.mean(costs)
        rows.append(
            {
                "method": method,
                "task_id": task,
                "run_count": len(runs),
                "task_speedup": score,
                "mean_model_cost_usd": cost,
                "speedup_per_dollar": score / cost,
            }
        )
    methods = {}
    for method in sorted({r["method"] for r in rows}):
        tasks = [r for r in rows if r["method"] == method]
        methods[method] = {
            "task_count": len(tasks),
            "run_count": sum(r["run_count"] for r in tasks),
            "speedup_at_4h": statistics.harmonic_mean(r["task_speedup"] for r in tasks),
            "mean_model_cost_usd": statistics.mean(r["mean_model_cost_usd"] for r in tasks),
            "mean_task_ratio": statistics.mean(r["speedup_per_dollar"] for r in tasks),
        }
    return methods, rows


def summarize_he(training: list[dict], validation: list[dict]) -> dict:
    def scores(rows, key):
        groups = defaultdict(lambda: defaultdict(list))
        for row in rows:
            reward = row["recorded_reward"]
            if not math.isfinite(reward) or reward < 0:
                raise ValueError("Invalid recorded reward")
            groups[row[key]][row["task_id"]].append(max(1.0, reward))
        return {
            str(group): statistics.harmonic_mean(
                statistics.geometric_mean(rewards) for rewards in tasks.values()
            )
            for group, tasks in sorted(groups.items())
        }

    return {
        "iterations": scores(training, "iteration"),
        "epochs": scores(training, "epoch"),
        "validation": scores(validation, "harness"),
    }


def curve_at(
    records: list[dict], times: list[float], *, recorded_time: bool = False
) -> list[list[float]]:
    """Return (seconds, mean cumulative cost, aggregate speedup) on a grid."""
    run_curves = []
    time_key = "elapsed_seconds" if recorded_time else "analysis_seconds"
    for run in sorted(records, key=lambda r: (r["task_id"], r["repeat"])):
        events = sorted(run["evaluations"], key=lambda e: e[time_key])
        event_times, best = [], []
        value = 1.0
        for event in events:
            value = max(value, candidate_speedup(run, event))
            event_times.append(event[time_key])
            best.append(value)

        def usage_time(u):
            value = u[time_key]
            return u["booked_elapsed_seconds"] if value is None else value

        usage = sorted(run["usage"], key=usage_time)
        usage_times = [usage_time(u) for u in usage]
        costs = [u["cost_usd"] for u in usage]
        sampled = []
        for t in times:
            # The archived figure stores minutes; converting back to seconds can
            # move an event by a floating-point ulp. Allow one microsecond here.
            i = bisect_right(event_times, t + 1e-6) - 1
            j = bisect_right(usage_times, t + 1e-6) - 1
            sampled.append((best[i] if i >= 0 else 1.0, costs[j] if j >= 0 else 0.0))
        run_curves.append((run["task_id"], sampled))
    output = []
    for index, t in enumerate(times):
        task_scores = defaultdict(list)
        cumulative_costs = []
        for task, sampled in run_curves:
            score, cost = sampled[index]
            task_scores[task].append(score)
            cumulative_costs.append(cost)
        score = statistics.harmonic_mean(
            statistics.geometric_mean(values) for values in task_scores.values()
        )
        output.append([t, statistics.mean(cumulative_costs), score])
    return output


def check_figure_curves(records: list[dict], figure: dict) -> None:
    for method, reference in figure["CURVES"].items():
        selected = [r for r in records if r["method"] == method]
        actual = curve_at(selected, [row[0] * 60 for row in reference])
        for observed, expected in zip(actual, reference, strict=True):
            compare(
                {"cost": observed[1], "score": observed[2]},
                {"cost": expected[1], "score": expected[2]},
            )
    selected = [r for r in records if r["method"] == "harness_evolution"]
    # The time panel first evaluates the recorded event sequence, then clips
    # its final-delivery x coordinates to 4h. This creates a vertical last step.
    reference = figure["HE_TIME"]
    actual = curve_at(selected, [row[0] * 60 for row in reference], recorded_time=True)
    for observed, expected in zip(actual, reference, strict=True):
        compare({"score": observed[2]}, {"score": expected[1]})
    reference = figure["HE_COST_CURVE"]
    actual = curve_at(selected, [row[0] * 60 for row in reference])
    for observed, expected in zip(actual, reference, strict=True):
        compare(
            {"cost": observed[1], "score": observed[2]},
            {"cost": expected[1], "score": expected[2]},
        )


def compare(actual: dict, expected: dict, *, tolerance=1e-8) -> None:
    if actual.keys() != expected.keys():
        raise ValueError("Result keys differ from the recorded paper snapshot")
    for key, value in expected.items():
        if isinstance(value, dict):
            compare(actual[key], value, tolerance=tolerance)
        elif not math.isclose(actual[key], value, rel_tol=tolerance, abs_tol=tolerance):
            raise ValueError(f"Result mismatch at {key}: {actual[key]} != {value}")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize_updates(root: Path, records: list[dict]) -> dict:
    """Check run joins and summarize logged events, without inferring edit quality."""
    summaries = {}
    for method in ("harness_scaling",):
        rows = load(root / f"results/reviews/{method}.json.gz")
        expected_runs = {r["run_id"] for r in records if r["method"] == method}
        if {r["run_id"] for r in rows} != expected_runs:
            raise ValueError(f"Update records do not cover the main cohort: {method}")
        if len({r["event_id"] for r in rows}) != len(rows):
            raise ValueError(f"Duplicate update event: {method}")
        summary = {
            "run_count": len(expected_runs),
            "event_count": len(rows),
            "events_per_run": dict(sorted(Counter(r["run_id"] for r in rows).items())),
        }
        summaries[method] = summary
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "generated")
    args = parser.parse_args()
    check_manifest(args.root)
    records = load_records(args.root / "results/main/records.jsonl.gz")
    contract = load(args.root / "manifest.json")["main"]
    expected_n = contract["task_count"] * contract["runs_per_task"]
    methods, task_rows = aggregate(records)
    if len(methods) != 4 or any(
        r["task_count"] != contract["task_count"] or r["run_count"] != expected_n
        for r in methods.values()
    ):
        raise ValueError("Main-result cohort does not match manifest")
    compare(methods, load(args.root / "results/main/reported.json"))
    check_figure_curves(records, load(args.root / "results/main/figure.json.gz"))
    he = summarize_he(
        load(args.root / "results/he/training.json"),
        load(args.root / "results/he/validation.json"),
    )
    reference = load(args.root / "results/he/reported.json")
    compare(he["iterations"], {str(i): x for i, x in enumerate(reference["training"], 1)})
    compare(he["epochs"], reference["epochs"])
    compare(he["validation"], {f"h{int(k):02d}": x for k, x in reference["validation"].items()})
    offline = load(args.root / "results/he/offline-cost.json")
    if not math.isclose(
        sum(s["cost_usd"] for s in offline["sessions"]), offline["total_cost_usd"], abs_tol=1e-8
    ):
        raise ValueError("Offline cost does not equal the sum of released session costs")
    ablation_records = load(args.root / "results/ablation/records.json")
    for run in ablation_records:
        if not math.isclose(
            run["recorded_model_cost_usd"] + run["additional_cost_usd"],
            run["final_cost_usd"],
            abs_tol=1e-10,
        ):
            raise ValueError(f"Ablation cost components disagree: {run['run_id']}")
    ablation, ablation_tasks = aggregate_scores(ablation_records)
    compare(ablation, load(args.root / "results/ablation/reported.json"))
    updates = summarize_updates(args.root, records)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output / "main-results.csv",
        [{"method": method, **result} for method, result in methods.items()],
    )
    write_csv(args.output / "task-results.csv", task_rows)
    write_csv(
        args.output / "ablation-results.csv",
        [{"method": method, **result} for method, result in ablation.items()],
    )
    write_csv(args.output / "ablation-task-results.csv", ablation_tasks)
    (args.output / "he-results.json").write_text(json.dumps(he, indent=2) + "\n")
    (args.output / "update-summary.json").write_text(json.dumps(updates, indent=2) + "\n")
    print("Checksums, main metrics/curves, ablations, HE scores/cost, update joins: PASS")
    for method, result in methods.items():
        print(
            f"{method}: {result['speedup_at_4h']:.3f}x; "
            f"${result['mean_model_cost_usd']:.2f}; "
            f"Speedup/$ {result['mean_task_ratio']:.3f}"
        )
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()
