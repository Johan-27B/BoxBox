#!/bin/bash
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${WORKSPACE:-/home/user/workspace}"
export TESTS_DIR WORKSPACE

export PATH="/usr/local/cargo/bin:${PATH}"

print_incorrect_result() {
    echo '{"correct": false, "value": null}'
}

echo "=== Build ==="
if ! (
    cd "$WORKSPACE/ccc"
    timeout 300 cargo build --release --quiet 2>/tmp/ccc-build.stderr
); then
    echo "Build: FAIL"
    tail -20 /tmp/ccc-build.stderr || true
    print_incorrect_result
    exit 0
fi

CCC="$WORKSPACE/ccc/target/release/ccc"
export CCC
echo "Build: OK"

echo
echo "=== Correctness ==="
if ! bash "$TESTS_DIR/test_correctness.sh"; then
    echo "Correctness: FAIL"
    print_incorrect_result
    exit 0
fi
echo "Correctness: PASS"

echo
echo "=== Performance ==="
bash "$TESTS_DIR/test_performance.sh"
