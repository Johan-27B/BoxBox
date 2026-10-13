"""WebSocket bridge between xterm.js and a tmux session."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import subprocess
import termios
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect


def _resize(fd: int, rows: int, cols: int) -> None:
    if rows <= 0 or cols <= 0:
        return
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


async def attach_tmux(
    websocket: WebSocket,
    tmux_name: str,
    *,
    accepted: bool = False,
    initial_rows: int = 0,
    initial_cols: int = 0,
) -> None:
    """Attach an interactive browser terminal to an existing tmux session."""
    if not accepted:
        await websocket.accept()
    master_fd, slave_fd = pty.openpty()
    _resize(master_fd, initial_rows, initial_cols)
    env = {**os.environ, "TERM": "xterm-256color"}
    process = subprocess.Popen(
        ["tmux", "attach-session", "-t", tmux_name],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        close_fds=True,
    )
    os.close(slave_fd)

    async def output_loop() -> None:
        while process.poll() is None:
            try:
                data = await asyncio.to_thread(os.read, master_fd, 65_536)
            except OSError:
                break
            if not data:
                break
            await websocket.send_bytes(data)

    async def input_loop() -> None:
        while process.poll() is None:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect
            data = message.get("bytes")
            if data is not None:
                os.write(master_fd, data)
                continue
            text = message.get("text")
            if text is None:
                continue
            if text.startswith("{"):
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict) and payload.get("type") == "resize":
                    _resize(
                        master_fd,
                        int(payload.get("rows") or 0),
                        int(payload.get("cols") or 0),
                    )
                    process.send_signal(signal.SIGWINCH)
                    continue
            os.write(master_fd, text.encode())

    tasks = [asyncio.create_task(output_loop()), asyncio.create_task(input_loop())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await task
        with suppress(OSError):
            os.close(master_fd)
        if process.poll() is None:
            process.terminate()
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=2)
