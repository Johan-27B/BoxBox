#!/usr/bin/env python3
"""Fire the 200-request MCP batch and time / hash the responses.

Used by tests/test_correctness.sh and tests/test_performance.sh.

Two modes:
  collect: run once, record responses, and print the canonical hash.
  time: run once and print wall-clock seconds.

Both modes assume the target MCP server is up on the given --port and
speaks the auth token in $AUTH_TOKEN.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def send(session: str, port: int, payload: dict, token: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": session,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    if not body.strip():
        return {}
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(body)


def initialize(port: int, token: str) -> str:
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "perfbench-runner", "version": "0.1"}}
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(init).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
        sid = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
    if not sid:
        raise RuntimeError("No Mcp-Session-Id from initialize")
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    send(sid, port, notif, token)
    return sid


def normalise(resp: dict) -> str:
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items()
                    if k.lower() not in ("sessionid", "session-id", "mcp-session-id")}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    return json.dumps(strip(resp), sort_keys=True, separators=(",", ":"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=Path, required=True)
    ap.add_argument("--mode", choices=["collect", "time"], required=True)
    ap.add_argument("--out", type=Path, help="Where to write JSONL responses in collect mode")
    ap.add_argument("--port", type=int, default=3000)
    args = ap.parse_args()

    token = os.environ.get("AUTH_TOKEN", "perfbench-probe-token")

    reqs = [json.loads(l) for l in args.requests.read_text().splitlines() if l.strip()]

    sid = initialize(args.port, token)

    t0 = time.perf_counter()
    responses = []
    for req in reqs:
        resp = send(sid, args.port, req, token)
        responses.append(resp)
    wall = time.perf_counter() - t0

    if args.mode == "time":
        print(f"{wall:.4f}")
        return 0

    # collect mode: write jsonl + canonical hash
    if not args.out:
        print("--out is required in collect mode", file=sys.stderr)
        return 2
    args.out.write_text("\n".join(json.dumps(r, sort_keys=True) for r in responses) + "\n")
    canonical = "\n".join(normalise(r) for r in responses)
    print(hashlib.sha256(canonical.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
