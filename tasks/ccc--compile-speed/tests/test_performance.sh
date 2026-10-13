#!/bin/bash
set -uo pipefail

NUM_WARMUP=1
NUM_RUNS=5
SOURCE="$TESTS_DIR/workload/sqlite3.c"
OUTPUT="/tmp/sqlite-perf.o"

measure_once() {
    local start end elapsed
    rm -f "$OUTPUT"
    start="$(date +%s.%N)"
    if ! timeout 180 "$CCC" -c "$SOURCE" -o "$OUTPUT" \
        >/tmp/sqlite-perf.stdout 2>/tmp/sqlite-perf.stderr; then
        return 1
    fi
    end="$(date +%s.%N)"

    if [ ! -s "$OUTPUT" ]; then
        return 1
    fi

    elapsed="$(awk -v start="$start" -v end="$end" 'BEGIN { printf "%.9f", end - start }')"
    printf '%s\n' "$elapsed"
}

for i in $(seq "$NUM_WARMUP"); do
    echo "  warmup $i"
    if ! measure_once >/dev/null; then
        echo "SQLite warmup compilation failed"
        echo '{"correct": false, "value": null}'
        exit 0
    fi
done

times=()
for i in $(seq "$NUM_RUNS"); do
    if ! elapsed="$(measure_once)"; then
        echo "SQLite timed compilation failed"
        echo '{"correct": false, "value": null}'
        exit 0
    fi
    echo "  run $i: ${elapsed}s"
    times+=("$elapsed")
done

read -r mean stdev cv <<EOF
$(printf '%s\n' "${times[@]}" | awk '
    {
        sum += $1
        sum_squares += $1 * $1
    }
    END {
        mean = sum / NR
        variance = NR > 1 ? (sum_squares - (sum * sum / NR)) / (NR - 1) : 0
        if (variance < 0) {
            variance = 0
        }
        stdev = sqrt(variance)
        cv = mean > 0 ? stdev / mean : 0
        printf "%.9f %.9f %.9f\n", mean, stdev, cv
    }
')
EOF

values="$(IFS=,; printf '%s' "${times[*]}")"
echo "[performance] mean = ${mean}s"
printf '{"correct":true,"value":%s,"details":{"values":[%s],"n_warmup":%d,"aggregator":"mean","stdev":%s,"coefficient_of_variation":%s}}\n' \
    "$mean" "$values" "$NUM_WARMUP" "$stdev" "$cv"
