#!/bin/bash
set -uo pipefail

EU="$SRC_DIR/eucalypt/target/release/eu"
PASS=true

# Run from the workload directory so relative input imports resolve.
run_workload() {
    local workload_dir="$1" day="$2" part="$3"
    ( cd "$workload_dir" && "$EU" "${day}.eu" -t "$part" 2>/dev/null ) \
        | grep -vE '^\s*$|^---' | tail -1
}

check_workload() {
    local workload_dir="$1" day="$2" part="$3" expected="$4"
    local name="${day}-${part}"
    local actual expect
    actual="$(run_workload "$workload_dir" "$day" "$part")"
    expect="$(cat "$expected")"
    if [ "$actual" != "$expect" ]; then
        echo "FAIL: $name — got '$actual', expected '$expect'"
        PASS=false
    else
        echo "PASS: $name"
    fi
}

check_workload "$TESTS_DIR/workload" day06 part-2 \
    "$TESTS_DIR/expected/day06-part-2.txt"
check_workload "$TESTS_DIR/heldout" day09 part-1 \
    "$TESTS_DIR/expected/day09-part-1.txt"
check_workload "$TESTS_DIR/heldout" day08 part-1 \
    "$TESTS_DIR/expected/day08-part-1.txt"

if [ "$PASS" = false ]; then
    echo "CORRECTNESS FAILED"
    exit 1
fi
echo "All correctness checks passed"
exit 0
