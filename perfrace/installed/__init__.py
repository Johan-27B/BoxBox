"""Task-specific integrations of agents with PerfRace."""

AGENT_IMPORT_PATHS = {
    "terminus-boxbox": "perfrace.installed.terminus_boxbox:TerminusBoxBoxAgent",
    "frozen": "perfrace.installed.frozen:FrozenHarnessAgent",
    "harness-evolution": "perfrace.installed.evolved:EvolvedHarnessAgent",
    "harness-scaling": "perfrace.installed.scaling:HarnessScalingAgent",
    "bounded-boxbox": "perfrace.installed.bounded:BoundedTerminusBoxBoxAgent",
    "periodic-boxbox": "perfrace.installed.periodic:PeriodicTerminusBoxBoxAgent",
}
