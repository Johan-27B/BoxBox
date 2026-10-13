from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from perfrace.curate.dashboard.terminal import attach_tmux


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is required")
def test_terminal_websocket_attaches_and_sends_input() -> None:
    tmux_name = f"perfrace-terminal-test-{uuid.uuid4()}"
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            tmux_name,
            "bash",
            "-c",
            "printf 'READY\\n'; read line; printf 'GOT:%s\\n' \"$line\"; sleep 5",
        ],
        check=True,
    )
    app = FastAPI()

    @app.websocket("/terminal")
    async def terminal(websocket: WebSocket) -> None:
        await attach_tmux(
            websocket,
            tmux_name,
            initial_cols=120,
            initial_rows=40,
        )

    try:
        with TestClient(app).websocket_connect("/terminal") as websocket:
            output = b""
            for _ in range(10):
                output += websocket.receive_bytes()
                if b"READY" in output:
                    break
            assert b"READY" in output

            size = ""
            for _ in range(20):
                size = subprocess.run(
                    [
                        "tmux",
                        "display-message",
                        "-p",
                        "-t",
                        tmux_name,
                        "#{window_width}x#{window_height}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                if size == "120x39":
                    break
                time.sleep(0.05)
            assert size == "120x39"

            websocket.send_text(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
            for _ in range(20):
                size = subprocess.run(
                    [
                        "tmux",
                        "display-message",
                        "-p",
                        "-t",
                        tmux_name,
                        "#{window_width}x#{window_height}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                if size == "100x29":
                    break
                time.sleep(0.05)
            assert size == "100x29"

            websocket.send_text("hello\n")
            for _ in range(10):
                output += websocket.receive_bytes()
                if b"GOT:hello" in output:
                    break
            assert b"GOT:hello" in output
    finally:
        subprocess.run(
            ["tmux", "kill-session", "-t", tmux_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
