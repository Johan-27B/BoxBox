#!/bin/bash
# PerfRace verifier entry point: build, correctness, then performance.
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_MCP="${AGENT_MCP:-/home/user/workspace/n8n-mcp}"
export TESTS_DIR AGENT_MCP

print_incorrect_result() {
    echo '{"correct": false, "value": null}'
}

# Build
echo "=== Build ==="
if ! ( cd "$AGENT_MCP" && npm run build >/tmp/n8n-build.log 2>&1 ); then
    echo "Build: FAIL"
    tail -20 /tmp/n8n-build.log || true
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
if ! bash "$TESTS_DIR/test_performance.sh"; then
    echo "Performance: FAIL"
    print_incorrect_result
    exit 0
fi
