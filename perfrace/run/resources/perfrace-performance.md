# PerfRace performance seccomp profile

`perfrace-performance.json` is derived from the Moby
`seccomp/v0.2.3` default profile. It adds one unconditional
`SCMP_ACT_ALLOW` rule for `perf_event_open`. Enabling
`performance_profile: {}` also adds only `CAP_PERFMON` to the Docker service;
it does not add `CAP_SYS_PTRACE`.

The task image must provide a host-compatible `perf` executable. For non-root
images, give the resolved executable the `cap_perfmon=ep` file capability so
it can activate the capability supplied in the container's bounding set.
Profiling works when the host sets:

```text
kernel.perf_event_paranoid = 2
```

The upstream profile already allows `ptrace`, `process_vm_readv`, and
`process_vm_writev` on supported kernels. PerfRace keeps the remaining
default seccomp restrictions unchanged.

On hosts with a small `kernel.perf_event_mlock_kb`, use a bounded perf ring
buffer such as:

```bash
perf record -m 1 -e cpu-clock -F 99 -g -- <command>
```

Source:
`https://github.com/moby/profiles/tree/seccomp/v0.2.3/seccomp/default.json`.
