# Optimize CCC compile speed

Our build workflow uses **CCC** (Claude's C Compiler), a C compiler written in
Rust, to compile the SQLite 3.46.0 amalgamation. This compile-to-object step is
taking too long. Please optimize CCC so it completes faster while continuing
to produce a functional object and compile general C programs correctly.

The workspace root contains the compiler source in `ccc/` and the SQLite
source and header in the read-only `workload/` directory.

## Build and run

Run these commands from the workspace root:

```bash
cargo build --release --manifest-path ccc/Cargo.toml
./workload/run.sh
```

Set `CCC_TIME_PHASES=1` when running `./workload/run.sh` to print compiler
phase timings.

## Requirements

- Edit only files under `ccc/`.
- Do not modify anything under `workload/`.
- Preserve the functionality of the generated SQLite object and CCC's
  behavior for other C programs.
- Improve the general compilation path rather than recognizing this source by
  its path, file name, contents, or digest.
- Do not embed, cache, or reuse a precomputed object file.

## Performance goal

Minimize the wall-clock seconds required by `./workload/run.sh`. Lower is
better.
