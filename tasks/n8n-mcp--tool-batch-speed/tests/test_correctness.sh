#!/bin/bash
set -euo pipefail

start_server() {
    cd "$AGENT_MCP"
    MCP_MODE=http AUTH_TOKEN=perfbench-probe-token PORT=3000 \
        node dist/mcp/index.js >/tmp/n8n-correctness.log 2>&1 &
    SERVER_PID=$!
    export SERVER_PID
    for _ in $(seq 40); do
        curl -fsS http://127.0.0.1:3000/health >/dev/null 2>&1 && return 0
        sleep 0.5
    done
    return 1
}

stop_server() {
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
}

check_case() {
    local name="$1" requests="$2"
    local actual expected
    actual="$(
        python3 "$TESTS_DIR/run_batch.py" \
            --requests "$requests" \
            --mode collect \
            --out "/tmp/n8n-${name}-responses.jsonl" \
            --port 3000
    )"
    expected="$(cat "$TESTS_DIR/expected/${name}.sha256")"
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $name - got $actual, expected $expected"
        return 1
    fi
    echo "PASS: $name"
}

trap stop_server EXIT
if ! start_server; then
    echo "FAIL: server did not become healthy"
    tail -30 /tmp/n8n-correctness.log || true
    exit 1
fi

check_case scored "$TESTS_DIR/workload/requests.jsonl"
check_case heldout "$TESTS_DIR/heldout/requests.jsonl"
