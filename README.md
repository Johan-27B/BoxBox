# BOXBOX

**Recursive Harness Self-Improvement for Long-Running Performance Optimization**

BOXBOX enables an agent to revise its own executable harness from task-specific experience while continuing an ongoing task.

## BOXBOX

- **Agent-controlled updates:** the task-solving agent decides when to spend its remaining budget on harness review.
- **Full-harness editing:** revisions can change tool implementations, control flow, and state management.
- **Kernel-managed hot reloading:** a separate kernel manages review, validation, activation, and recovery while preserving execution context.

## PerfRace

PerfRace is a benchmark of 100 performance-optimization tasks from real-world software projects across seven workload domains. Agents iteratively modify project code and request correctness and performance feedback within a task budget. Tasks do not require reference optimizations.

## Release status

This repository currently contains an overview. Code, benchmark assets, and reproduction instructions are not yet included.
