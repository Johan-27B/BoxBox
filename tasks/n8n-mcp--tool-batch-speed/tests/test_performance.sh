#!/bin/bash
# Measure one complete server lifecycle and 200-request MCP batch per run.
set -euo pipefail

NUM_WARMUP=2
NUM_RUNS=5
RUN_SCRIPT="$TESTS_DIR/workload/run.sh"

run_once() {
    local start end
    start="$(date +%s.%N)"
    if ! timeout 120 env AGENT_MCP="$AGENT_MCP" "$RUN_SCRIPT" \
        >/tmp/n8n-performance.stdout 2>/tmp/n8n-performance.stderr; then
        cat /tmp/n8n-performance.stderr >&2
        return 1
    fi
    end="$(date +%s.%N)"
    awk -v start="$start" -v end="$end" \
        'BEGIN { printf "%.9f\n", end - start }'
}

for _ in $(seq "$NUM_WARMUP"); do
    run_once >/dev/null
done

times=()
for i in $(seq "$NUM_RUNS"); do
    elapsed="$(run_once)"
    echo "  run $i: ${elapsed}s"
    times+=("$elapsed")
done

python3 - "${times[@]}" <<'PY'
import json
import statistics
import sys

times = [float(value) for value in sys.argv[1:]]
mean = statistics.mean(times)
stdev = statistics.stdev(times) if len(times) > 1 else 0.0
cv = stdev / mean if mean else None
print(f"[performance] mean = {mean:.6f}s (from {len(times)} runs)")
print(f"[performance] all runs = {times}")
print(
    json.dumps(
        {
            "correct": True,
            "value": mean,
            "details": {
                "values": times,
                "n_warmup": 2,
                "aggregator": "mean",
                "stdev": stdev,
                "coefficient_of_variation": cv,
            },
        }
    )
)
PY
