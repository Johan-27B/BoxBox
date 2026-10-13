---
name: perfrace-pair-verification
description: Construct and pair-verify one repository as a trustworthy PerfRace instance.
---

# PerfRace Pair Verification

Turn one repository into one machine-evaluable PerfRace instance.
Construction drives the session. The agent investigates and executes; the
human intervenes at the Realism, Reliability, and Integrity review gates,
then makes the final `ACCEPT`, `REVISE`, or `REJECT` decision.

The durable evidence and human-facing task guide are the single
`$PERFRACE_INSTANCE_ROOT/<instance-id>/report.md`, created from
`./REPORT_TEMPLATE.md`. When the variable is unset, the launcher defaults to the
repository's `instances/` pivot workspace.

## Working agreement

- Persist code, task files, and operational report sections in English.
  Realism, Integrity, Reliability, and final-decision evidence in `report.md`
  are deliberate Chinese-language sections.
- Build in this order: `Explore & Design`, `Build & Calibrate`,
  `Validate Integrity`, `Finalize`.
- Stop only when a review's construction and report evidence are ready. Give a
  one-screen Chinese brief covering the claim, essential context, grounded
  evidence, uncertainty, and recommendation; allow discussion or added probes
  before presenting `Approve` or `Reject`.
- Reopen a review and every dependent stage when later evidence invalidates an
  approved claim.
- Keep raw run artifacts under `data/`; link stable job names and measurement
  paths rather than copying large logs.
- If a claim cannot be supported by project sources or a runnable probe, mark
  it as unknown and ask the human for evidence or a decision.

## Output

```text
$PERFRACE_INSTANCE_ROOT/<instance-id>/
  report.md
  instruction.md
  task.toml
  environment/
    Dockerfile
    workspace/
      <project>/
      workload/
        run.sh
  tests/
    workload/
    heldout/
    expected/
    test.sh
    test_correctness.sh
    test_performance.sh
    ...
```

The accepted task pins an immutable GHCR image. The complete pinned project
source and visible workload already exist in the task package. Its Dockerfile
copies that workspace into the image; it must not download project source or
workload inputs during the build.

## Fixed constraints

| Constraint | Rule |
|---|---|
| Verification time | All scored warmups/repetitions and held-out runs must fit within 1200 seconds with practical headroom. |
| Measurement signal | Target at least 3 seconds per timed execution. For shorter operations, enlarge the real input or user batch; proceed only with repeated CV ≤10% and a signal clearly above noise. Never loop a micro-operation solely to inflate runtime. |
| Image size | The final uncompressed image must be ≤3 GiB (`3221225472` bytes), measured with `docker image inspect`; assume evaluators have no cached layers. |
| Repetitions | Use `repetition_scope = "internal"`; one shadow performs all warmups and timed runs, retains raw values, aggregates them, and emits one result. |
| CPU placement | Declare only `[environment].cpus` and inherit the host allocator's cpuset. Never use fixed CPU IDs, `taskset`, `numactl --physcpubind`, `sched_setaffinity`, or Docker cpuset overrides. Profiling-supported thread-count limits remain valid when they do not select CPUs. |
| Runtime parallelism | Execution providers, process-wide and session-level thread counts, spin policies, and runtime scheduling options are part of the frozen resource and measurement protocol. Calibrate them before the candidate run and enforce the same effective policy for baseline, candidate, correctness, and performance from task-owned read-only setup. A candidate may not earn reward solely by changing this policy unless runtime configuration was explicitly approved as the user-facing optimization surface. |
| Candidate build | Compilation, linking, or packaging required only to materialize edits to the target project is setup and must remain outside the timed metric. A build-like command may be timed only when the target project itself provides compiler, build, code-generation, or analysis capability to users and processes an independently grounded real user or downstream input rather than rebuilding its own editable source. |
| Agent setup | The final image must provide executable `bash`, `git`, and `python3`, a usable system CA trust store for Python's default TLS context, and `tmux` with working `new-session -e KEY=value` support. Verify these as the image's default user before publication. |

### Build reuse across repetitions

For runtime workloads, perform one fresh candidate build per verifier shadow
before correctness and performance execution. Reuse the resulting target and
task-owned runner artifacts across correctness, warmups, and timed repetitions.
Between repetitions, reset only the mutable state and outputs required to make
each declared user operation independent. Record build time as setup and keep
the measurement timer around the user operation only.

## Stage 1 — Explore & Design

Understand the project and select a real workload before constructing the task:

- explain what the project does, who uses it, and which user workflows are
  performance-sensitive;
- use upstream documentation, examples, benchmarks, issues, and telemetry only
  to discover candidate paths. Score only a reproducible real user or downstream
  operation with independently grounded data and scale; never score target-repo
  tests, benchmarks, examples, demos, fixtures, generated stress cases, or
  synthesized microbenchmarks. A small custom driver may only replay that real
  workload;
- do not select the target project's own release, CI, packaging, or self-build
  merely because maintainers wait for it. Build-like workloads require a target
  whose user-facing product is compilation, building, generation, or analysis,
  exercised on independent real user or downstream input;
- prefer open sources; when permission is required, record a brief
  justification in `report.md` and continue verification without blocking;
- measure the target project's relevant clean and incremental compilation
  early in exploration, including the rebuild required after a representative
  source edit. If repeated project compilation would consume a disproportionate
  share of the curation or evaluation budget, narrow the package, target, or
  enabled features, establish a reusable dependency cache, or park/reject the
  candidate before Realism review instead of discovering the cost later;
- before cloning or materializing, estimate checkout, submodule/LFS, dependency,
  build-artifact, workload, image-size, runtime, and signal feasibility against
  the fixed constraints above; resize the real workload or reject the candidate
  before Realism review when they are not plausible;
- compare plausible real workload candidates rather than selecting the first
  convenient operation;
- run the selected workload end to end on the unmodified project and identify
  the project execution path it exercises;
- repeat a lightweight pilot of that unmodified workload under a representative
  resource profile to estimate runtime, CV, and signal-to-noise before building
  the instance. Treat this only as a feasibility estimate, not final Reliability
  evidence; diagnose, rescope, park, or reject before Realism review when CV is
  likely to exceed 10% or meaningful improvements would be hidden by noise;
- before requesting Realism review, list the existing instance root and choose
  an unused final instance id that follows the rules below;
- propose the exact operation, fixture provenance and scale, visible scored
  workload, independent verifier copy, additional correctness cases,
  correctness utility, measurement boundary, metric, and direction.

### Early feasibility gate

Before Realism review, obtain the exact grounded input, trace its user path,
and run one end-to-end unmodified pilot. Record phase times, confirm meaningful
target-owned signal, estimate build/image/verifier cost, then present a concise
Realism brief or PARK/REJECT recommendation.

### Instance ID

Before Realism review, choose the shortest unused `<repo>--<workload>` id.

- Match `^[a-z0-9][a-z0-9-]*--[a-z0-9][a-z0-9-]*$`. Use the repository name
  unless an owner resolves a collision; remove punctuation and language
  suffixes such as `.jl`.
- Use the fewest workload words needed for identification and omit generic
  terms such as `benchmark`, `performance`, `workload`, and `speed`.
- Check the instance root and active reports, record the unused id in front
  matter, and keep it stable after Realism approval.

### Human review — Realism

Explain what the project does, who uses it, the selected execution path, why
the workload operation, data, and scale are real, and which alternatives were
considered or rejected. Present grounded evidence, utility, metric, and
remaining unknowns, then ask whether this is meaningful project performance
work. Pause for the Human decision before constructing the canonical package.

## Stage 2 — Build & Calibrate

After Realism approval:

- retain the approved `<repo>--<workload>` id and construct the canonical task
  package in staging, including the pinned project, visible workload, executable
  `workload/run.sh`, Dockerfile, instruction, task config, report, and verifier;
- make the image copy the packaged workspace, start in `/home/user/workspace`,
  and keep only the target project writable;
- enforce the fixed constraints in the final package and record the measured
  image size and complete internal measurement protocol before Reliability review;
- place an independent byte-identical scored input under `tests/workload/`,
  additional correctness inputs under `tests/heldout/`, and expected data
  under `tests/expected/`. Repository-native cases may be used only for
  held-out correctness, never as either scored-workload copy;
- keep task-owned runners, binaries, caches, and outputs outside the editable
  project, and pin the base image, source revision, dependencies, fixtures,
  and expected outputs;
- write `instruction.md` as the end user's real optimization request, using
  paths relative to `/home/user/workspace` and stating the exact build and
  `workload/run.sh` commands, editable boundary, behavior contract, metric,
  direction, and anti-special-casing requirement without exposing evaluation
  internals;
- make correctness enforce only the observable utility of the declared
  workload. Do not require upstream native tests, repository-wide typechecks,
  existing APIs, file layout, implementation structure, or architecture to
  remain intact. The agent may replace or reorganize the implementation
  freely when the workload utility is preserved;
- retain ordinary files from the pinned upstream tree, including its
  benchmarks, profiling, roadmaps, prompts, and known attempts; remove `.git`,
  private construction artifacts, gold solutions, and verifier-only data;
- run `perfrace lint`, build a fresh image, execute scored and additional
  correctness cases, and confirm instruction and verifier behavior agree;
- validate cheapest-first: local probes, one workload run, targeted
  correctness, one fresh image build, then the complete verifier. Batch related
  changes before the fresh build and reuse that image for tests/report updates;
- build the candidate implementation before performance measurement. The timer
  must start only around the declared user operation, and
  `environment/workspace/workload/run.sh` must not compile or rebuild the
  editable target merely to make candidate changes take effect;
- use freeform builds, profiling, timing experiments, and repeated correctness
  while debugging, detecting flaky verdicts or semantic output early;
- use pilot measurements to choose warmups, repetitions, aggregation, and
  repetition scope from observed behavior and variance;
- retain phase timings that demonstrate candidate build, dependency setup, and
  verifier preparation are outside the reported performance value. A speedup
  caused only by generic self-rebuild cache or compilation configuration is not
  optimization evidence for a runtime workload;
- investigate setup, I/O, external services, scheduling, NUMA, and cache
  dominance with phase timings, `host_resources`, and controlled runs;
- on a fresh unmodified image, adjust representative workload scale and timeout
  so the signal is measurable and complete verification fits within 1200
  seconds with headroom;
- calibrate CPU, memory, and storage, then freeze the workload, correctness
  contract, measurement protocol, resources, and timeout before fresh-building
  the final evaluable image;
- record the final resource profile, then use the launcher-provided paired
  command for one nop baseline and at most one full candidate-agent attempt on
  that exact protocol, capped at 1,800 seconds unless the Human approves more;
- treat the candidate as a bounded optimization-feasibility probe, not a search
  for the best reward. One correct, repeatable gain is sufficient and ends
  candidate work;
- judge an incorrect or no-gain candidate from its trajectory, not its verdict
  alone. If it understood the instruction and pursued a reasonable optimization,
  retain it as valid feasibility evidence without rejecting the instance or
  launching another agent search. Revise or reject only when the trajectory
  exposes a task, instruction, verifier, or agent-actionability failure;
- save the candidate changes as `data/candidate.patch`; retain the raw results
  and record the job, trials, verdict, speedup, stop reason, and nop CV, which
  must remain within 10%;
- debug repeated candidate measurements by replaying the saved patch. After a
  protocol-only change, rerun the nop baseline and replay that patch; rerun the
  agent only when changed task behavior or instructions invalidate the original
  trajectory.

Use one Linux x86-64 profile:

| Profile | vCPU | Memory | Storage |
|---|---:|---:|---:|
| `small` | 2 | 8 GiB | 10 GiB |
| `standard` | 4 | 16 GiB | 20 GiB |
| `large` | 8 | 32 GiB | 40 GiB |

Start with `small` and use the smallest profile with measured runtime, memory,
storage, and stability headroom. Record evidence for each upgrade; nonstandard
resources require Reliability approval. Do not use a larger profile merely to
lower CV; diagnose the variance first and upgrade only when the smaller profile
demonstrably constrains the declared workload. Keep public network mode for the
model endpoint while keeping the project and workload self-contained.

Choose aggregation to match the metric semantics: use mean for expected
cumulative cost and median when the metric represents a typical run.

### Variance diagnosis

When measurement CV exceeds 10%, do not immediately increase workload size,
repetition count, resource profile, or switch aggregation. First identify which
phase and resource produces the variance:

- correlate per-phase timings with total time, then use host-allocation metadata
  and controlled runs to separate setup, I/O, service, scheduling, NUMA, and
  measured-process variance;
- increase CPU, memory, or storage only when measurements show that the current
  profile constrains the declared operation, such as CPU throttling, memory
  pressure, or I/O saturation. A larger profile producing a lower CV is not by
  itself sufficient evidence;
- inspect native numerical, compression, database, and language-runtime thread
  pools. CPU quota does not bound runnable threads, so oversubscription can
  reduce both speed and stability;
- when profiling confirms a thread-pool cause, sweep counts from one through
  the allocated vCPUs on the same workload and choose the smallest stable
  setting that does not materially regress the operation. This calibration is
  task setup, not candidate optimization;
- encode the selected provider, thread counts, spin behavior, and scheduling
  policy in a task-owned read-only launcher, then rerun correctness and
  fresh-image measurements under the final protocol. Enforce and record the
  effective runtime values: environment variables alone are insufficient when
  library APIs such as ONNX Runtime `SessionOptions` can override them;
- reject or invalidate a candidate reward caused only by changing these frozen
  runtime controls, including moving the same work onto more runnable threads,
  changing the execution provider, or altering process-wide thread
  oversubscription. Never use thread limits to conceal a weak signal or
  setup-dominated workload.

### Human review — Reliability

Ask whether equivalent builds and runs support the same verdict and measurement.
Present fresh-build correctness, raw values, dispersion, verification time,
resources, and the candidate trajectory. One correct repeatable gain is
sufficient; an incorrect result remains acceptable when the trajectory shows
understanding and a reasonable optimization.

## Stage 3 — Validate Integrity

After Reliability approval:

- compare the instruction requirements with verifier checks in both directions;
- audit the scoring boundary: matching visible and verifier-owned workload
  copies, agent-writable paths and outputs, private artifacts, expected data,
  caches, and reward inputs. Rebuild fixed verifier runners independently;
- audit configuration-only reward paths. Distinguish approved product
  configuration from changes to the frozen protocol, semantic trade-offs, or
  work shifted outside the timed boundary;
- run an explicit red-team hacking pass that attempts leaked-data access,
  verifier-input or expected-output modification, success-shaped failures,
  partial or empty work, hard-coded visible answers, workload-specific
  precomputation, frozen thread/provider-policy overrides through source,
  environment, config, or runtime session APIs, and reward-path bypasses.
  General precomputation remains valid when the declared workload utility is
  preserved;
- count a trial only when a materially distinct, successfully applied invalid
  solution reaches the final verifier. Static audits, leaf-checker probes,
  failed or no-op mutations, and unrelated syntax or build failures do not
  count as verifier rejection. After hardening, replay the same attack and
  record its final verdict;
- rerun lint and correctness after integrity hardening. If any change affects
  the workload, image, verifier execution path, measurement protocol, resource
  profile, or timing, reopen Reliability and recalibrate before requesting
  Integrity review.

### Human review — Integrity

Ask whether an invalid, leaked, incomplete, or shortcut implementation can
receive a valid score. Present the boundary audit and red-team results. Visible
upstream and scored-workload data are allowed; verifier ownership means an
independent immutable copy, not secrecy.

## Stage 4 — Finalize

After Integrity approval:

- summarize all review decisions and limitations in `report.md`; leave Agent
  cost and Human comments for launcher synchronization;
- clean the instance to the canonical package shown above. Remove scratch,
  logs, patches, profiler output, downloads, temporary scripts, build artifacts,
  duplicate fixtures, and unrelated files; keep durable evidence under host
  `data/`;
- identify the exact local image and release files, then run final lint and
  end-to-end checks;
- confirm that no credential, host-only dependency, hidden answer, required
  untracked input, or file outside the minimal release package remains.

Ask the human for one disposition:

- `ACCEPT & PUBLISH INSTANCE`
- `REVISE`
- `REJECT`

On `REJECT`, keep the candidate and all curation artifacts. Record the reason
in `report.md`; after the worker exits, the manager archives the workspace at
`$PERFRACE_INSTANCE_ROOT/.reject/<run-id>/<session-id>/`. Do not publish it or
delete its evidence automatically.

`ACCEPT & PUBLISH INSTANCE` authorizes one release. From the current staging
workspace:

1. Confirm that `oras version` reports exactly `1.3.3`.
2. Run
   `perfrace publish . --image <exact-local-image> --repository <ghcr-repo>`.
3. The command snapshots the package, pushes and verifies the image, finalizes
   `task.toml` and `report.md` only inside that snapshot, and builds the
   deterministic task archive.
4. It attaches the archive to the image as a GHCR OCI artifact, pulls it into
   an empty directory, verifies the package hash, and runs `perfrace lint`.
5. Only after every step succeeds does it update live `task.toml`, write
   `$PERFRACE_INSTANCE_ROOT/.releases/<instance-id>.json`, and finally write
   live `report.md` as `ACCEPT`. Earlier failures leave the live package
   non-ACCEPT.

Do not manually tag or push the image, upload a task tarball, embed release
digests inside the package, or mark ACCEPT around individual steps.

Publish an existing ACCEPT instance with
`perfrace publish /absolute/path/to/<instance-id>`; it reuses the immutable
image already pinned in `task.toml`, so do not pass `--image` or `--repository`.
Publish missing releases from the formal root in bounded, idempotent batches
with `perfrace publish --all-accepted --instance-root <root>`. Existing
instances reuse their pinned image and do not rerun the candidate or semantic
reviews.

After publishing or withdrawing releases, run
`perfrace export-releases --instance-root <root>` from the repository checkout
and verify that the catalog exactly matches the active `.releases/*.json`
records.

## Report lifecycle

1. Start from `REPORT_TEMPLATE.md` in the session staging workspace. Keep only
   its canonical front-matter fields and enum values; put qualifications in the
   body rather than inventing combined states.
2. Keep operational guidance in `Overview`, `Run`, `Files`, and `Scoring`;
   leave review conclusions and Human decisions visible, with long evidence in
   `<details>`.
3. Update the report before every blocking review and set completion metadata
   only after the final decision.
4. After worker exit, the manager promotes ACCEPT to the instance root or
   archives REJECT under `.reject/<run-id>/<session-id>/`.

## Hard failures

Reject or revise while any condition remains:

- the workload lacks real user or downstream grounding, uses prohibited
  target-repo cases, or is a synthesized microbenchmark;
- utility, instruction, measurement boundary, and reward do not describe the
  same task;
- failure, partial work, hard-coding, writable verifier data, or private
  construction leakage can bypass correctness;
- required source, fixtures, dependencies, or the final image cannot be
  reproduced from the complete task package;
- a fixed constraint remains unsatisfied, correctness is flaky, meaningful
  improvements are hidden by noise, or verification cannot finish clearly
  within the approved profile;
- the candidate trajectory shows that the instruction is not understandable
  or actionable. An incorrect verdict alone is not a hard failure.
