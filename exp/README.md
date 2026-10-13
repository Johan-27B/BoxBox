# Experimental Artifacts

This directory provides the numeric records for the main results, offline
Harness Evolution, and ablation experiments, alongside HE harness versions and
HS round metadata.

## Contents

| Location | Contents |
| --- | --- |
| `results/main/records.jsonl.gz` | Evaluation events, usage, and costs for Frozen Harness, Harness Evolution, Harness Scaling, and BOXBOX: 50 tasks and three runs per method/task. |
| `results/main/figure.json.gz` | Figure 1 plotting values and run-resampling intervals. |
| `results/main/reported.json` | Reference metrics for checking recomputed results. |
| `results/he/` | Per-run training and validation rewards, selected-version results, and offline model costs. |
| `results/ablation/` | Per-run scores and costs for Bounded BOXBOX, Periodic BOXBOX, and BOXBOX on the 14-task subset. |
| `results/reviews/` | Run-linked HS round metadata. |
| `harnesses/he/` | H0–H24 source snapshots and their version index. |
| `scripts/` | Metric recomputation and plotting. |
| `manifest.json` | Metric definitions, analysis conventions, and file checksums. |

The compressed records contain numeric observations and stable run/task
identifiers. Analysis does not require model access, task containers, or the
complete benchmark. Source snapshots are linked by generation in
`harnesses/he/index.json`.

## Reproduce

From the repository root:

```bash
uv sync
uv run python exp/scripts/analyze.py
uv run python exp/scripts/plot_main.py
uv run python exp/scripts/plot_he.py
```

The `exp/` directory can also be copied and analyzed on its own: metric
recomputation uses only the Python standard library, and plotting requires
Matplotlib and NumPy.

Outputs are written to `exp/generated/`. The analysis script checks file hashes,
recomputes main-result metrics and curve values from run records, and verifies
ablation metrics, HE training/validation scores, offline cost, and update-record
joins. The main plot uses the archived
curve and interval values; the HE plot computes scores from per-run rewards.
Inter is used when installed, with DejaVu Sans as the portable fallback.

## Records and aggregation

Each main-result record identifies its method, task, repeat, baseline, budget,
evaluation events, cumulative usage, and full-run model cost. Evaluation events
include the verdict, metric value, recorded elapsed time, and analysis time.
Usage records include cumulative cost and, where available, token counts.
Missing request timestamps remain `null`, with their booking time stored
separately.

The run score is its best accepted speedup within the analysis budget, with the
unmodified project contributing a floor of 1. Task scores are geometric means
across runs; benchmark speedup is their harmonic mean. Speedup/$ is the arithmetic
mean of each task's score divided by that task's mean run cost.

Training iteration *i* evaluates H(*i*−1) on five tasks and produces H*i*.
Iterations 1–8, 9–16, and 17–24 each cover the 40 training tasks. Validation
evaluates H8, H16, and H24 on ten tasks with three runs per task; H24 is used
for the released HE test results.

The ablation records contain endpoint scores rather than evaluation event
sequences. Each variant has three runs on each of 14 tasks. Recorded model cost,
any additional cost, and the reported total are separate fields.

## Harness Scaling round records

`results/reviews/harness_scaling.json.gz` contains 2,141 round entries from
the 150 HS runs, with measurements, revision lineage, and available execution,
evolution, and transition timestamps. These timestamps are wall-clock seconds
relative to each HS run's recorded start, not the cumulative task-budget clock.
Missing timestamps and successor revisions remain `null`.

Round records join to main-result records through `run_id`. Revision labels such
as `h000` are local to a run; equal labels across runs do not imply equal source
code. These records contain metadata, not the corresponding source diffs or full
trajectories. HE source snapshots are provided separately under `harnesses/he/`.

## Result metadata

[`manifest.json`](manifest.json) specifies token prices, aggregation, and
time and cost accounting rules, including boundary handling, estimated
timestamps, and additional cost components. Records retain observed and analysis
times separately, along with full-run costs and cumulative usage.
[`results/he/offline-cost.json`](results/he/offline-cost.json) records offline
cost coverage and its lower-bound status.
