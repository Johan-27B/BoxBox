# Experiment Configuration

## Shared initial harness

The initial harness H0 is `boxbox/terminus_boxbox/harness/`. BOXBOX, Frozen
Harness, and Harness Scaling start from independent copies of these files.
Offline Harness Evolution initializes its training repository from the same
source. The BOXBOX kernel and PerfRace evaluator are outside the editable source.

The source-copy operation does not change prompts or tool implementations.
H0 uses a 60-second per-command wait limit and completion-marker detection.
The four methods share the official Judge and task-budget accounting.
Set the same target model and reasoning effort when comparing methods.

`harness_source` selects a different source directory. For BOXBOX, Frozen
Harness, and HS, `harness_revision` can select a Git revision when that source
is a Git repository root. Each resulting copy remains independent.

## Frozen Harness and BOXBOX

The bundled `tasks/` directories can be used directly with `--path`;
passing `--path tasks` selects all available tasks. Each task includes a complete Dockerfile and
`environment/workspace/` with project source and workload. PerfRace builds
the environment locally; the task's `tests/` supplies the official checks
and evaluation data. The initial build downloads public base images and
dependencies, without requiring a prebuilt task image.

Configure the endpoint through `LLM_BASE_URL` and `LLM_API_KEY`, and replace the
model placeholder in the YAML:

```bash
uv run perfrace run -c configs/iclr2027/frozen.yaml --path tasks/<task-id>
uv run perfrace run -c configs/iclr2027/boxbox.yaml --path tasks/<task-id>
```

Both retain task context across official evaluations. Frozen Harness exposes
submission but no `boxbox()` action, and runtime faults do not launch a review.
BOXBOX permits agent-triggered revision and kernel-managed recovery.

## Harness Scaling

```bash
uv sync --extra evolution
uv run --extra evolution perfrace run -c configs/iclr2027/harness-scaling.yaml \
  --path tasks/<task-id>
```

HS runs an attempt, obtains an official measurement, and invokes an external
evolver using that attempt's trajectory, terminal output, and project changes.
After validating the proposed harness, it starts a fresh agent session with the
original task instruction. Project files and their Git history persist;
conversation and terminal-session state are not transferred. A retained
harness revision also starts a fresh session.

The default attempt limit is 1,500 seconds, configured by
`job.agents[].kwargs.max_attempt_timeout_sec`. Attempts, evolution, and official
evaluation share the configured task budget. Invalid evolution retains the
current harness. Round records, harness snapshots, and evolution evidence are
written under the trial's `agent/harness-scaling/` directory.

Task sources may reside entirely in the GHCR image. The integration reads the
configured project workdir inside the container and does not require a
host-side copy of the task workspace.

## Offline Harness Evolution

Configure:

- `configs/iclr2027/he-run.yaml`: endpoint and target-run settings.
- `configs/iclr2027/harness-evolution.yaml`: model, task catalog, split, source,
  generation schedule, and stage budgets.

The default protocol has 24 updates, batches of five training tasks, 45-minute
training runs, and validation of generations 8, 16, and 24. Validation and test
use three four-hour runs per task. Concurrency defaults to one and is configurable.

The configured split manifest is a JSON object:

```json
{
  "schema_version": 1,
  "catalog_sha256": "<SHA-256 of the configured release catalog>",
  "train": ["<training task IDs>"],
  "validation": ["<validation task IDs>"],
  "test": ["<test task IDs>"]
}
```

IDs must occur in the release catalog, the groups must be disjoint, and their
sizes must match the configuration. Task packages are resolved below
`instance_root`. The selected catalog and split must be supplied before
launching the pipeline; they are not inferred from directory order.

Harness code executes on the host. Review the source and explicitly set
`protocol.trust_evolved_code: true` to acknowledge this before running HE.
The meta-agent's file tools restrict access to its supplied source and evidence;
this is not a sandbox for executing arbitrary evolved Python.

```bash
uv run --extra evolution perfrace evolve-harness \
  -c configs/iclr2027/harness-evolution.yaml --dry-run

uv run --extra evolution perfrace evolve-harness \
  -c configs/iclr2027/harness-evolution.yaml --stop-after-training

uv run --extra evolution perfrace evolve-harness \
  -c configs/iclr2027/harness-evolution.yaml --resume
```

Each training iteration evaluates a harness on its assigned batch, diagnoses
the observed trajectories and measurements, and proposes the next revision.
The controller validates and commits changes. Held-out validation selects a
revision; the pipeline then emits a separate test configuration and launch
script under `<artifact_root>/<experiment_name>/test/`. Test execution does not
perform further harness optimization.

The output includes versioned harness sources, train-batch manifests, scores,
diagnostic reports, meta-agent trajectories, selection records, and usage
summaries. Resume checks the saved configuration and artifact identities before
continuing.

## Ablations

Bounded and Periodic are separate implementations in `perfrace/ablations/`.
Their adapters deploy the same H0 files as BOXBOX. Variant-specific behavior is
applied when loading the initial harness and each successor; it is not patched
into the editable source. Both reuse the core validation, state transfer,
rollback, official evaluation, and task-budget handling.

```bash
uv run perfrace run -c configs/iclr2027/bounded-boxbox.yaml --path tasks/<task-id>
uv run perfrace run -c configs/iclr2027/periodic-boxbox.yaml --path tasks/<task-id>
```

**Bounded BOXBOX** keeps agent-triggered reviews. During each review, the agent
declares one failure mechanism and one predefined scope: target guidance,
tools/observability, context/memory, runtime control, or review policy. Multiple
files may change to implement that single revision. A changed harness without
a declaration is rejected; keeping the harness unchanged needs no declaration.
Transition records include the declaration, candidate diff, and a path-level
audit. The audit flags obvious cross-scope edits but does not enforce semantic
separation inside shared Python files; those changes require semantic review.

**Periodic BOXBOX** keeps full-harness editing and replaces the voluntary
`boxbox()` tool with an external schedule. The default interval is 1,800 seconds,
configurable through `job.agents[].kwargs.review_interval_sec`. A due review
waits for the current tool interaction to finish; an official submission takes
precedence. The clock starts with task execution, persists across submissions,
and restarts after each review or fault-recovery transition. It uses elapsed
wall time, including intervening evaluation time, and does not queue missed
intervals. Final delivery disables scheduled reviews. Transition records identify
scheduled reviews separately from faults and report any delay to a safe boundary.

## Results

The [released experimental artifacts](../exp/README.md) include main-result and
ablation records, HE training/validation results and versioned harness sources,
and HS round metadata, with scripts for recomputing metrics and plotting
the results.

All candidate methods use PerfRace's official correctness and performance
evaluation. `perfrace plot <run-directory>` reads the resulting run records.
Preserve the configuration, task identifiers, harness revision, and model
usage alongside each result when collecting experiments.
