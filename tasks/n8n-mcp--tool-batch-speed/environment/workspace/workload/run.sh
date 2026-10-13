#!/bin/sh
set -eu

root=/home/user/workspace
token=workload-probe-token
server_log=/tmp/n8n-mcp-server.log
responses=/tmp/n8n-mcp-responses.jsonl

cleanup() {
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}

cd "$root/n8n-mcp"
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

AUTH_TOKEN="$token" python3 "$root/workload/client.py" \
    "$root/workload/requests.jsonl" >"$responses"
