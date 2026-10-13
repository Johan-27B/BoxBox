#!/bin/sh
set -eu

TESTS_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
AGENT_MCP="${AGENT_MCP:?}"
token=perfbench-probe-token
server_log=/tmp/n8n-mcp-performance-server.log
responses=/tmp/n8n-mcp-performance-responses.jsonl

cleanup() {
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}

cd "$AGENT_MCP"
MCP_MODE=http AUTH_TOKEN="$token" PORT=3000 \
    node dist/mcp/index.js >"$server_log" 2>&1 &
server_pid=$!
trap cleanup EXIT INT TERM

ready=false
for _ in $(seq 40); do
    if curl -fsS http://127.0.0.1:3000/health >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 0.5
done

if [ "$ready" != true ]; then
    cat "$server_log" >&2
    exit 1
fi

AUTH_TOKEN="$token" python3 "$TESTS_DIR/workload/client.py" \
    "$TESTS_DIR/workload/requests.jsonl" >"$responses"

test "$(wc -l <"$responses")" -eq 200
