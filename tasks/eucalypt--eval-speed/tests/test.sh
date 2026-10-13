#!/bin/bash
# PerfRace verifier entry point: build, correctness, then performance.
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="${SRC_DIR:-/home/user/workspace}"
export TESTS_DIR SRC_DIR

# Keep Cargo available when a login shell resets PATH.
export PATH="${CARGO_HOME:-/usr/local/cargo}/bin:${HOME:-/root}/.cargo/bin:$PATH"

print_incorrect_result() {
    echo '{"correct": false, "value": null}'
}

# Build
echo "=== Build ==="
if ! ( cd "$SRC_DIR/eucalypt" && cargo build --release --quiet 2>/tmp/eu_build.log ); then
    echo "Build: FAIL — interpreter does not compile"
    tail -20 /tmp/eu_build.log || true
    print_incorrect_result
    exit 0
fi
echo "Build: OK"

# Correctness
echo ""
echo "=== Correctness Test ==="
if bash "$TESTS_DIR/test_correctness.sh"; then
    echo "Correctness: PASS"
else
    echo "Correctness: FAIL"
    print_incorrect_result
    exit 0
fi

# Performance
echo ""
echo "=== Performance Test ==="
bash "$TESTS_DIR/test_performance.sh"
