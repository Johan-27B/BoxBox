#!/usr/bin/env python3
"""Send one JSONL request batch to a running n8n-mcp HTTP server."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def post(port: int, token: str, payload: dict, session_id: str | None = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id is not None:
        headers["Mcp-Session-Id"] = session_id

    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode()
        returned_session = (
            response.headers.get("Mcp-Session-Id")
            or response.headers.get("mcp-session-id")
        )

    if not body.strip():
        return {}, returned_session
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:]), returned_session
    return json.loads(body), returned_session


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: client.py <requests.jsonl>", file=sys.stderr)
        return 2

    port = int(os.environ.get("PORT", "3000"))
    token = os.environ.get("AUTH_TOKEN", "workload-probe-token")
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "workload-runner", "version": "0.1"},
        },
    }
    _, session_id = post(port, token, initialize)
    if not session_id:
        raise RuntimeError("No Mcp-Session-Id from initialize")

    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    post(port, token, initialized, session_id)

    requests = Path(sys.argv[1]).read_text().splitlines()
    for line in requests:
        if line.strip():
            response, _ = post(port, token, json.loads(line), session_id)
            print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
