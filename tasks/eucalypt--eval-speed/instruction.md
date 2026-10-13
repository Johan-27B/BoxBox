# Optimize eucalypt program execution

Our workflow uses **eucalypt**, a Rust implementation of a functional language
for structured data, to run the program in `workload/day06.eu`. This program's
`part-2` target is taking too long to complete. Please optimize the interpreter
so this execution finishes faster without changing its result or eucalypt's
general behavior.

The workspace root contains the interpreter source in `eucalypt/` and the
program and its input files in the read-only `workload/` directory.

## Build and run

Run these commands from the workspace root:

```bash
cargo build --release --manifest-path eucalypt/Cargo.toml
./workload/run.sh
```

The program imports files relative to its own directory, so use
`workload/run.sh` for the complete execution.

## Profiling

Adding `-S` to the interpreter invocation in `workload/run.sh` prints VM
metrics and timing information to stderr. Release builds include debug
symbols, and `perf`, `samply`, `flamegraph`, `rustfilt`, and `cargo-show-asm`
are available.

## Requirements

- Edit only files under `eucalypt/`.
- Do not modify anything under `workload/`.
- Preserve the program's output and the interpreter's behavior for other
  eucalypt programs.
- Do not add logic that recognizes this program, its path, file name,
  contents, inputs, or result.
- Do not return cached or precomputed output instead of interpreting the
  program normally.

## Performance goal

Minimize the wall-clock seconds required by `./workload/run.sh`. Lower is
better.
