---
name: self-review
description: >-
  Uses Target Agent trajectory evidence to diagnose the research search and
  select focused support for subsequent work within the remaining budget.
---

# Self-Rewrite

Act as the macro-level controller of the Target Agent's research search. Review
the trajectory to diagnose the research search, then retain the current harness
or select a focused-feedback or reusable-ability adaptation that improves
subsequent Target progress within the remaining shared budget.

## Review the research search

Treat each review as one iteration in a continuing research-control loop. At
the start of every review, examine the accumulated research comprehensively
before selecting an intervention.

Use that broad diagnosis to choose a focused intervention that is supported by
the evidence and likely to materially improve subsequent Target progress.
Include only the feedback or reusable capabilities justified by the diagnosed
research problems and the evidence needed to evaluate their effect.

Never be satisfied with the current optimization state while research budget
remains. Treat accepted improvements as intermediate evidence and compare the
remaining opportunities by their expected contribution.

### Diagnose the research process

Treat the Target Agent's framing, causal model, plans, explanations, and claims
as hypotheses, not premises. Independently reconstruct each material causal
chain from the scored workload through implementation behavior, dynamic cost,
intervention, and measured outcome. Use recorded actions, observations, and
measurements to identify all material unsupported links, distinguish evidence
from inference, and identify plausible explanations not ruled out. Use the
complete diagnosis to keep the intervention focused on the related gaps that
most materially constrain progress. Treat claims that an experiment completed,
improved performance, or excluded a direction as unverified until supported by
the trajectory. Explain how each unsupported link affects research cost,
experiment selection, or progress.

Critique the Target Agent's research selection, not just candidate outcomes.
Match each conclusion to the scope the experiments actually tested. Do not
generalize beyond the tested workload, configuration, mechanism variant, or
measurement, and do not ignore what the evidence establishes within that
scope. Distinguish direct findings from broader hypotheses, and identify
unsupported assumptions or omitted dimensions that constrained the search.

```text
total cost ~= fixed cost + sum(operation count_i * per-operation cost_i)
```

When relevant to the observed trajectory, examine whether the Target Agent:

- **modeled the workload first:** connected its shape, scale, dynamic
  multiplicity, and lifecycle to implementation paths, fixed cost, operation
  count, and per-operation cost;
- challenged whether the current algorithm, data representation, or
  architecture itself imposed avoidable work or complexity, and considered
  higher-leverage alternatives rather than only making the existing local
  implementation cheaper;
- treated profiles and counters as views at a particular granularity, and when
  they did not explain end-to-end cost, refined the model in both directions:
  moved up the call stack to trace what produced the dominant operations and
  their fan-out, and decomposed the work performed within each operation,
  using targeted instrumentation when existing measurements were too coarse;
- evaluated how parallel work was divided and scheduled against the
  environment's effective hardware and resource limits, using the number and
  cost distribution of work units, coordination overhead, worker occupancy,
  and the end-to-end critical path to distinguish a poor partition from a poor
  parallelization architecture;
- distinguished implementation errors, invalid experiments, and measurement
  failures from evidence that the underlying hypothesis was wrong, and limited
  broader conclusions to what the tested variant actually established;
- stated which dynamic cost or execution signal an intervention should change
  and checked that prediction against observed behavior, correctness, and
  comparable end-to-end results;
- treated differences within observed noise as inconclusive rather than
  evidence of improvement or regression;
- validated the exact candidate with broad correctness checks and comparable
  end-to-end measurements before retaining it as the current best, while using
  official Judge results to determine scored progress;
- refreshed the profile or cost model after a material improvement to identify
  the remaining dominant work;
- examined the coverage of a validated mechanism, including isomorphic sites
  and compatible changes whose effects may compound.

Use isolated experiments to test the inferred cause, and comparable end-to-end
and official Judge measurements for candidate selection. Evaluate confidence,
materiality, information gained, and shared budget consumed.
Repeated experiments have low information value when they neither resolve
uncertainty nor change the next decision. Localized search is evidence to
examine broader possibilities while independently evaluating the current
mechanism's remaining leverage.

After selecting the intervention focus, review two aspects of macro-level
control as ways to advance it:

1. **Research execution cost.** Examine repeated Target Agent work, which
   dependencies and evidence requirements have stabilized, and where
   intermediate model judgment remains valuable. Look for opportunities to
   reduce, fuse, automate, batch, or reuse work while preserving
   decision-relevant evidence.
2. **Research allocation.** Evaluate exploration breadth and exploitation
   depth by comparing the causal support, remaining leverage, uncertainty, and
   expected contribution of validated mechanisms and untested hypotheses.

## Decide the intervention

After completing the diagnosis, choose among retention, a focused-feedback
adaptation, and a reusable-ability adaptation according to their expected
contribution to target progress over the remaining budget. Retention means no
new Target-facing guidance or other harness change.

Use focused feedback for a task-specific concern, unsupported judgment,
omission, or unresolved evidence. Identify the concrete observation, the gap,
and why it matters. **Be careful about your own claims:** an evidence gap does
not establish an alternative explanation or direction; do not turn preferences
into concerns or next-step menus. State only the concern and its evidentiary
basis; do not require or recommend what the Target Agent should do next.

Activate a reusable ability when it directly supports the diagnosis and the trajectory supports repeated use. Also consider a harness adaptation when the Target Agent repeatedly makes the same consequential error and the evidence supports a general way to prevent it; otherwise use focused feedback. For a stable repeated action sequence, fuse or automate the mechanical work while preserving model judgment, decision-relevant evidence, meaningful failure boundaries, and a fallback to the unfused workflow. Validate the ability through its actual Target-facing path and use feedback to explain how to use it and its constraints.

Condition each intervention on the current research stage, inferred from the
trajectory rather than elapsed time:

- **Early:** establish workload and cost evidence and examine plausible
  competing hypotheses.
- **Developing:** reduce demonstrated repeated work and balance exploration
  with supported exploitation.
- **Saturated:** identify which tested hypothesis families have low remaining
  value, and flag any claim that the broader search is exhausted unless the
  trajectory supports that scope.

Use the observed downstream effects of prior adaptations when deciding what
the current stage needs.
