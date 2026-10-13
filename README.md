# BOXBOX

Code, settings, and data for the paper's main experiments, ablations, and PerfRace benchmark.
All paths below are relative to the repository root.

## Main experiments

The main experiments compare BOXBOX with Frozen Harness, Harness Scaling, and
offline Harness Evolution. They share the initial harness in
`boxbox/terminus_boxbox/harness/` and the PerfRace evaluator in `perfrace/run/`.

| Method | Implementation | Settings |
| --- | --- | --- |
| BOXBOX | `boxbox/terminus_boxbox/` | `configs/iclr2027/boxbox.yaml` |
| Frozen Harness | `perfrace/installed/frozen.py` | `configs/iclr2027/frozen.yaml` |
| Harness Scaling | `perfrace/installed/scaling.py` | `configs/iclr2027/harness-scaling.yaml` |
| Harness Evolution | `perfrace/evolution/` (training and validation); `perfrace/installed/evolved.py` (test) | `configs/iclr2027/harness-evolution.yaml`; `configs/iclr2027/he-run.yaml` |

The evaluation configs specify a four-hour budget and three runs per task.
Model selection, reasoning effort, budget, and repetitions are configured through
`job.agents[].model_name`, `job.agents[].kwargs.reasoning_effort`,
`task_budget_sec`, and `job.n_attempts`. The endpoint and credential are supplied
through `LLM_BASE_URL` and `LLM_API_KEY`.

For HE, `harness-evolution.yaml` specifies the model, task catalog, train/validation/test
split, and stage-specific budgets and repetitions. `he-run.yaml` supplies the
agent-run template, including endpoint and reasoning-effort settings.

### Experimental data

| Experiment / result | Data | Contents |
| --- | --- | --- |
| Main comparison | `exp/results/main/records.jsonl.gz` | Evaluation events, model usage, and costs for all four methods: 50 tasks × 3 runs × 4 methods |
| Main-result metrics | `exp/results/main/reported.json` | Speedup, model cost, and Speedup/$ by method |
| Figure 1 | `exp/results/main/figure.json.gz` | Speedup–time and speedup–cost curves with uncertainty bands |
| HE training | `exp/results/he/training.json` | Per-task rewards for 24 iterations, with five tasks per iteration |
| HE validation | `exp/results/he/validation.json` | H8, H16, and H24 rewards on ten tasks, with three runs per task |
| HE offline cost | `exp/results/he/offline-cost.json` | Training and validation cost records and coverage |
| HE harness versions | `exp/harnesses/he/h00/`–`h24/` | Initial and evolved harness source snapshots; `index.json` records their lineage |
| HS execution rounds | `exp/results/reviews/harness_scaling.json.gz` | Per-round measurements, revision lineage, and timestamps |

## Ablation studies

Both ablations use the same initial harness and evaluator as BOXBOX.

| Ablation | Implementation | Settings |
| --- | --- | --- |
| Bounded BOXBOX: predefined editing scope | `perfrace/ablations/bounded.py` | `configs/iclr2027/bounded-boxbox.yaml` |
| Periodic BOXBOX: scheduled reviews | `perfrace/ablations/periodic.py` | `configs/iclr2027/periodic-boxbox.yaml` |

The periodic review interval is set by `job.agents[].kwargs.review_interval_sec`.
Bounded review scopes and their checks are defined in `perfrace/ablations/bounded.py`.

### Experimental data

`exp/results/ablation/records.json` contains per-run scores and costs for Bounded
BOXBOX, Periodic BOXBOX, and full BOXBOX on the 14-task subset, with three runs
per task. `exp/results/ablation/reported.json` contains the aggregate results.

For both main and ablation results, `exp/manifest.json` specifies aggregation,
time and cost accounting, and artifact checksums.

## PerfRace benchmark

- **Tasks:** `tasks/<task-id>/` contains the project source, workload, and official
  checks. Each task's `task.toml` specifies its resources and measurement protocol.
- **Construction:** `perfrace/collect/` implements discovery and filtering;
  `perfrace/curate/` implements agent–human Pair Verification. Stage models and
  endpoint settings are configured in `configs/settings.yaml`.

Framework attribution and local modifications: [Harbor](docs/HARBOR.md).
