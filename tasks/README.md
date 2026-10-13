# PerfRace Tasks

PerfRace evaluates agents on long-running performance optimization of real-world
software projects. The tasks available here are drawn from the formal benchmark.
The full benchmark will be released in `PerfRace-Bench` after the anonymous review period.

## Tasks

| Task ID | Project | Language | Workload |
| --- | --- | --- | --- |
| `eucalypt--eval-speed` | Eucalypt | Rust | Interpreter execution of the `day06` program |
| `ccc--compile-speed` | Claude's C Compiler | C | Compiling the SQLite amalgamation to an object file |
| `n8n-mcp--tool-batch-speed` | n8n-mcp | TypeScript | Processing a batch of 200 MCP tool calls |

Each task is a complete, Git-versioned package containing the instruction, task
metadata, Dockerfile, pinned project source, workload, and official evaluation
checks and inputs. PerfRace builds the task environment locally; access to a
prebuilt PerfRace image is not required.

`catalog.json` records the project revisions, public base images, and task-package
checksums.

## Run

From the `BOXBOX/` repository root, install the dependencies, configure the model
and provider in the run configuration, and select a task:

```bash
uv sync
uv run perfrace run -c configs/iclr2027/boxbox.yaml \
  --path tasks/eucalypt--eval-speed
```

To run all available tasks, pass `--path tasks`. The same task packages
work with the Frozen Harness, Harness Scaling, Bounded BOXBOX, and Periodic BOXBOX
configurations. Add `--dry-run` to inspect the resolved configuration without
starting containers or making model calls.

The first run builds the image from `environment/Dockerfile`, downloading its
public base image and build dependencies. Subsequent runs can reuse the local
image. To build a task separately, run:

```bash
docker build -t perfrace-eucalypt \
  tasks/eucalypt--eval-speed/environment
```

This standalone build checks the recipe; `perfrace run` manages its own image
names and build cache.

Eucalypt requests 2 CPUs; CCC and n8n-mcp request 4 CPUs. All three request 16 GiB of
memory, and CCC additionally specifies 20 GiB of writable storage. PerfRace's
isolated evaluation also needs host resources for its shadow environment.
Storage-quota enforcement requires a compatible Docker backing filesystem;
task resource limits are not silently reduced on unsupported hosts.

The task packages use Harbor's task format with `[perfrace.measurement]` metadata.
Correctness checks and performance measurements are performed by the official
PerfRace Judge.

## Package layout

```text
<task-id>/
├── instruction.md
├── task.toml
├── environment/
│   ├── Dockerfile
│   └── workspace/
│       ├── <project>/
│       └── workload/
└── tests/
```

The editable project and fixed workload are copied into the container by the
Dockerfile. Correctness and performance checks remain outside the agent's
workspace. Project source and vendored workload dependencies are tracked in Git;
upstream Git history, local build outputs, and caches are not.

## Third-party sources

Task packages include upstream source and workload assets with their original
license and copyright notices.

- **Eucalypt:** interpreter and program inputs from `curvelogic/eucalypt`,
  including the `day06` workload and additional correctness-check inputs.
  The upstream project remains the source of its licensing terms.
- **Claude's C Compiler:** compiler source from `anthropics/claudes-c-compiler`,
  with its [original license](ccc--compile-speed/environment/workspace/ccc/LICENSE).
  The workload uses SQLite 3.46.0; its notices remain in
  `ccc--compile-speed/tests/workload/sqlite3.c` and `sqlite3.h`.
- **n8n-mcp:** server source and node/template catalog from `czlonkowski/n8n-mcp`,
  with its [original license](n8n-mcp--tool-batch-speed/environment/workspace/n8n-mcp/LICENSE).
  The workload exercises the server through a fixed batch of MCP tool calls.
