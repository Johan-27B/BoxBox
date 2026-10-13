---
name: autoresearch
description: Uses Git to keep iterative hypotheses isolated, addressable, and recoverable.
---

# Skill: AutoResearch

Use Git as the research state. Keep `main` as the current candidate delivered
for official measurement, and test each hypothesis on its own `try/*` branch.

## Hypothesis exploration

Choose hypotheses by expected removable end-to-end workload cost, not by
implementation ease or hotspot share alone. Before implementing, estimate the
affected operation count, avoidable cost per operation, and overlap with other
costs.

Mechanically prove materiality before creating each `try/<hypothesis>` branch.
The runtime intentionally provides no project-specific cost model. On `main`,
write and run a project-specific estimator at:

```text
.autoresearch/tools/estimate_upper_bound.py
```

Have it emit `.autoresearch/estimates/<hypothesis>.json`, and add
`.autoresearch/` to `.git/info/exclude` so research machinery never enters the
candidate patch. The estimate must use fresh evidence from the current `main`,
not intuition or a profile percentage. Measure at least three comparable
end-to-end baseline samples and gather the project-specific operation counts,
timings, or microbenchmarks needed to price both removed work and new overhead.
Record every raw measurement command in the JSON.

The JSON contract is:

```json
{
  "schema_version": 1,
  "hypothesis": "<name without try/>",
  "base_commit": "<full current main commit>",
  "estimator": {
    "path": ".autoresearch/tools/estimate_upper_bound.py",
    "sha256": "<sha256 of the estimator>"
  },
  "baseline": {
    "command": "<end-to-end workload command>",
    "samples_seconds": [1.0, 1.0, 1.0],
    "median_seconds": 1.0,
    "noise_seconds": 0.0
  },
  "cost_model": {
    "affected_operations": 1,
    "avoidable_cost_per_operation_seconds": 1.0,
    "removable_fraction": 1.0,
    "added_overhead_seconds": 0.0,
    "uncertainty_seconds": 0.0,
    "estimated_gain_seconds": 1.0,
    "lower_bound_seconds": 1.0,
    "materiality_threshold_seconds": 0.05
  },
  "measurement_commands": ["<raw evidence command>"],
  "assumptions": ["<falsifiable cost-model assumption>"]
}
```

Compute `median_seconds` from the samples and compute `noise_seconds` as
`1.4826 * median(abs(sample - median_seconds))`. Compute:

```text
estimated_gain_seconds =
    affected_operations
    * avoidable_cost_per_operation_seconds
    * removable_fraction
    - added_overhead_seconds
lower_bound_seconds = estimated_gain_seconds - uncertainty_seconds
materiality_threshold_seconds =
    max(0.05 * median_seconds, 2 * noise_seconds)
```

Proceed only when `lower_bound_seconds >= materiality_threshold_seconds`.
The runtime independently recomputes these values, checks the estimator hash
and current `main` commit, and blocks the entire branch-creation command batch
when the record is missing, stale, malformed, or immaterial. Create `try/*`
branches only with literal `git checkout -b`, `git switch -c`, or `git branch`
commands; do not hide branch creation behind variables, scripts, or aliases.

Profiles and internal metrics may explain where cost occurs and why a
hypothesis could remove it, but they cannot establish that the evaluated cost
will decrease. Only comparable end-to-end workload measurements can establish
improvement.

## Budget-aware decision loop

Use a short evidence cycle instead of an open-ended stream of edits. At the
start of a direction, state the dominant cost source, the operation-count or
per-operation prediction, and the end-to-end signal that should move. Establish
a comparable baseline before editing when the workload permits it; distinguish
cold setup from the steady-state regime and keep the raw samples.

For each hypothesis, make one focused change, run the smallest correctness
check that can reject it, and then run comparable end-to-end samples. Keep the
change only when the end-to-end result and correctness support the prediction;
otherwise record why it failed and return to clean `main`. Do not spend a phase
repeating the same source inspection, noisy timing, or final scope audit. If two
plausible directions fail or remain within noise, move up the call stack or
inside the dominant operation to find a different cost source instead of
rephrasing the same hypothesis. Use narrow commands and targeted output when
large listings would crowd out the decision evidence.

Once a clean candidate has a correctness-preserving end-to-end improvement
whose margin clears the observed noise and materiality gate, stop exploring,
leave that exact candidate ready for measurement, and request completion. Do
not spend the remaining phase budget on speculative coverage or cosmetic
cleanup before the candidate is measured. Conversely, do not request completion
for a clean baseline, a profile-only signal, or an inconclusive/noisy result;
continue with the next highest-value falsifiable direction.

At every phase boundary, preserve the best known candidate explicitly: either
keep its commit on `main` or restore clean `main` before starting the next
direction. A timeout or interrupted command is not evidence of a result; inspect
the workspace and re-establish the candidate state rather than replaying an
ambiguous command.

## Checkpoint and final-delivery evidence

When a verifier checkpoint or measurement result is available, inspect the exact
measured commit and its correctness evidence before changing the workspace. Keep
an accepted candidate only when the timing is attributable to a source state that
can be identified and reproduced: an unchanged tree, a shell-interrupted run,
an unexplained timing discontinuity, or a profile-only signal is not a speedup.
Record the fastest *supported* accepted candidate mentally and in Git history,
and do not let a later experiment leave `main` slower or less trustworthy than
that candidate. Start each new hypothesis from the preserved best candidate, and
restore it after a rejected, noisy, or slower experiment.

After a checkpoint has established a clean, correctness-preserving candidate,
continued research is optional rather than mandatory. Continue only with a
falsifiable direction whose expected gain justifies its cost; otherwise finish
with the preserved candidate. Before final delivery, recheck `git status`, the
candidate commit, and the local correctness/end-to-end evidence. Final delivery
must not include speculative edits made solely because the phase remains open.
If the latest accepted measurement is slower than an earlier supported one,
restore the earlier supported candidate instead of treating final delivery as a
new research opportunity.

## Research history
Official measurements are recorded automatically on the exact measured target
commit under the `perfrace-measurements` Git notes ref. Each entry contains
`target_commit` and the complete `measurement`. When `harness_commit` is
present, use it to correlate target results with harness runtime versions.

If an interrupted agent phase leaves a dirty worktree, measurement recording
may create a synthetic commit under `refs/perfrace/measurement-snapshots/`.
That commit captures the measured tree without moving the current branch or
changing the worktree; its note also records the original `base_commit` and
`workspace_state=dirty_snapshot`.

Keep local research experience under the separate `perfrace-research` Git
notes ref. Never write local results, hypotheses, or interpretations to
`perfrace-measurements`.

When selecting a material hypothesis, append a concise `status=investigating`
entry to the current commit before implementation so the direction survives an
unexpected interruption. Include a stable hypothesis name, the evidence that
motivated it, and the next concrete experiment. When the experiment has a
commit, attach a final `kept`, `discarded`, `unmeasured`, or `blocked` entry to
that commit with the local evidence and resulting implication.

```bash
git notes --ref=perfrace-research append \
  -m "hypothesis=<name> status=investigating evidence=<why> next=<experiment>" HEAD
git log --all --show-notes=perfrace-research --show-notes=perfrace-measurements
```

Inspect both refs alongside target history before choosing the next hypothesis.
Multiple measurements and research entries may remain attached to one commit.
Keep entries compact and factual; do not store command transcripts. Branches
and commits remain the code record, while research notes preserve active
reasoning that may not yet have produced a commit. Git notes do not change the
target worktree.

## Hypothesis transaction

Start one branch from `main` for each hypothesis:

```bash
git checkout main
git checkout -b try/<hypothesis-name>
```

Explore and iterate freely within that hypothesis. Before concluding it, run
the relevant local correctness checks and end-to-end measurement. Commit the
result so the attempt remains addressable. Compare the observed end-to-end
change with the estimate's `estimated_gain_seconds` and record the prediction
error and its cause in the final `perfrace-research` note. Revise the
project-specific estimator before the next hypothesis when the error reveals a
bad operation count, hidden overlap, omitted overhead, or unstable noise model.
Use repeated prediction failures to revise the cost model and research strategy.

Promote only when the exact checkout being committed builds, passes
correctness, and improves the evaluated end-to-end workload relative to the
current `main` commit by an amount distinguishable from observed measurement
noise. Use profiles and internal metrics to explain the result, not as a
substitute for the evaluated end-to-end workload.

Keep a supported hypothesis by merging it into `main`:

```bash
git add -A
git commit -m "<hypothesis>: <before> -> <after> -- kept"
git checkout main
git merge --ff-only try/<hypothesis-name>
```

Committing or merging does not trigger official verification. Continue
research until an official measurement has enough expected information value
to justify its charged runtime. Then confirm that the candidate to measure is
clean and coherent, call `task_complete`, review the runtime's confirmation,
and call `task_complete` again. Official verification runs before the research
loop resumes.

Discard an unsupported hypothesis by leaving its commit on the unmerged branch:

```bash
git add -A
git commit -m "<hypothesis>: <before> -> <after> -- discarded: <reason>"
git checkout main
```

After a discard, continue exploration from clean `main` in the same turn. Do
not enter idle merely because a hypothesis was discarded; unchanged `main`
does not need verification.

Do not modify an accepted `main` directly, combine unrelated hypotheses in one
branch, or recreate failed work from memory when its branch can be inspected.
