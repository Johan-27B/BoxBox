# Harbor Attribution and Local Patches

## Upstream base

BOXBOX and PerfRace build on [Harbor](https://github.com/harbor-framework/harbor),
including its Terminus 2 agent, terminal interfaces, and evaluation framework.
Credit for these components belongs to the Harbor authors and contributors.

| Item | Value |
|---|---|
| Upstream repository | `harbor-framework/harbor` |
| Base commit | [`459ff6ec99417589b7f679d14ddf3b3f0ae4f1dc`](https://github.com/harbor-framework/harbor/commit/459ff6ec99417589b7f679d14ddf3b3f0ae4f1dc) |
| Package version at that commit | `0.20.0` |
| Vendored location | [`vendor/harbor/`](../vendor/harbor/) |
| Upstream license | [Apache License 2.0](../vendor/harbor/LICENSE) |
| Upstream citation metadata | [`CITATION.cff`](../vendor/harbor/CITATION.cff) |

The vendored package is a modified distribution, not an unmodified Harbor release.
The commit above identifies its upstream base; the package version alone does not
identify the local patches. Upstream license and attribution files are retained.
Harbor's license does not by itself assign a license to the original BOXBOX code.

## Local patch inventory

The following changes are maintained by this project for BOXBOX and PerfRace.
Paths in the table are relative to `vendor/harbor/`.

| Patch | Function and boundary | Modified files |
|---|---|---|
| Dependency integration | Removes Harbor's nested workspace/plugin source declarations and disables its default development dependency group, allowing the vendored base package to be installed through this repository's dependency configuration. | `pyproject.toml` |
| Conversation state transfer | Adds `Chat.dump_state()` and `Chat.load_state()`, plus deferred state loading in Terminus 2. Restores validated conversation messages into a fresh chat without copying usage counters or provider response-chain state. BOXBOX manages the surrounding runtime and terminal-session transfer. | `src/harbor/llms/chat.py`; `src/harbor/agents/terminus_2/terminus_2.py` |
| Budget-driven evaluation dispatch | Adds `AgentConfig.task_budget_sec` and dispatches configured tasks to PerfRace's `CheckpointTrial`, allowing repeated submissions within a shared budget without requiring task-defined steps. The evaluation loop itself lives outside Harbor. | `src/harbor/models/trial/config.py`; `src/harbor/trial/trial.py` |
| Baseline execution policy | Adds `scale_with_attempts` to avoid multiplying fixed-role trials by the candidate run count, and `cacheable` to identify eligible trials. Cache lookup and persistence are implemented in PerfRace, not Harbor. | `src/harbor/models/trial/config.py`; `src/harbor/job.py` |
| Docker snapshot access | Adds `commit_service()` and `resolve_service_container_id()` for capturing container state and identifying the correct Compose service. PerfRace uses these helpers to construct shadow evaluations. | `src/harbor/environments/docker/docker.py` |
| Effective CPU visibility | Exposes `effective_cpus` after task/job resource overrides so PerfRace can allocate matching evaluation resources. | `src/harbor/environments/base.py` |
| Docker storage limits | Adds storage-limit capability reporting and forwards positive `storage_mb` values to Docker Compose's writable-layer quota configuration. A value of zero omits the quota; positive requested limits are not silently downgraded. Enforcement requires a compatible Docker backing filesystem. | `src/harbor/environments/capabilities.py`; `src/harbor/environments/docker/__init__.py`; `src/harbor/environments/docker/docker.py`; `docs/content/docs/tasks/managing-resources.mdx` |
| Verifier timeout propagation | Passes the resolved call timeout as `verifier_timeout_sec` to custom verifiers, keeping their internal operations aware of the enclosing timeout. Harbor's built-in verifier receives no additional keyword. | `src/harbor/trial/trial.py` |
| Repeated mounted-log synchronization | Calls `prepare_logs_for_host()` on each mounted-log synchronization rather than treating the first synchronization as final. This makes later outputs available during iterative evaluation. | `src/harbor/trial/trial.py` |

The BOXBOX kernel and PerfRace's evaluation loop, baseline cache, shadow verifier,
and task packager are project-owned integration code outside `vendor/harbor/`.
They are not presented as upstream Harbor features.

## Validation and maintenance

Relevant regression tests include:

- Conversation state: `vendor/harbor/tests/unit/llms/test_chat.py` and
  `tests/perfrace/run/agents/test_terminus_boxbox.py`.
- Evaluation dispatch and budgets: `tests/perfrace/run/test_checkpoint_trial.py`.
- Baseline policy and caching: `tests/perfrace/run/test_runner.py`,
  `tests/perfrace/run/test_job.py`, and `tests/perfrace/run/test_cache.py`.
- Shadow evaluation and resource handling: `tests/perfrace/run/test_verifier.py`,
  `tests/perfrace/run/test_shadow_resources.py`, and
  `vendor/harbor/tests/unit/environments/test_docker.py`.
- Mounted-log synchronization: `vendor/harbor/tests/unit/test_trial_cleanup.py`.

The checked-in vendor tree already contains the patches; installation requires no
separate patch-application step. When updating Harbor, compare against the pinned
upstream commit, review each affected interface, rerun the relevant tests, and
update this inventory. Test paths above identify coverage, not a claim that every
upstream test suite has been run.

Other dependencies retain their own licenses and notices. Resolved dependency
versions are recorded in `uv.lock`. The optional `evolution` dependency group
provides NexAU for the external harness-evolution agents; their adapted prompts
and configurations have a separate [attribution notice](../perfrace/evolution/agents/NOTICE.md).
