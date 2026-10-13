#!/bin/bash
# Measure day-06 part-2 wall-clock time.
set -euo pipefail

NUM_WARMUP=1
NUM_RUNS=3

EU="$SRC_DIR/eucalypt/target/release/eu"

DAY="day06"
PART="part-2"
EXPECTED="$(cat "$TESTS_DIR/expected/day06-part-2.txt")"

run_one() {
    local output="/tmp/eucalypt-eval-perf.out"
    local start end actual
    start=$(date +%s.%N)
    ( cd "$TESTS_DIR/workload" && "$EU" "${DAY}.eu" -t "$PART" >"$output" 2>/dev/null )
    end=$(date +%s.%N)
    actual="$(grep -vE '^\s*$|^---' "$output" | tail -1)"
    if [ "$actual" != "$EXPECTED" ]; then
        echo "FAIL: timed workload produced '$actual'" >&2
        return 1
    fi
    echo "$end - $start" | bc -l
}

# Warmup is not included in the result.
for i in $(seq "$NUM_WARMUP"); do
    run_one >/dev/null
done

times=()
for i in $(seq "$NUM_RUNS"); do
    elapsed=$(run_one)
    echo "  run $i: ${elapsed}s"
    times+=("$elapsed")
done

python3 - "${times[@]}" <<'PY'
import json
import statistics
import sys

times = [float(t) for t in sys.argv[1:]]
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
                "n_warmup": 1,
                "aggregator": "mean",
                "stdev": stdev,
                "coefficient_of_variation": cv,
            },
        }
    )
)
PY
