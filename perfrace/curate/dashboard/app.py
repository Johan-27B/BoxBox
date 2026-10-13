"""FastAPI application for the localhost Pair Verification dashboard."""

from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from perfrace.curate.dashboard.files import (
    MARKDOWN_SUFFIXES,
    list_directory,
    read_file_range,
    render_markdown,
)
from perfrace.curate.dashboard.manager import DashboardManager
from perfrace.curate.dashboard.terminal import attach_tmux

STATIC_ROOT = Path(__file__).resolve().parent / "static"


class CandidateRequest(BaseModel):
    repo_url: str = Field(min_length=1)


class ImportRequest(BaseModel):
    content: str


def create_app(
    manager: DashboardManager,
    *,
    access_token: str,
    allowed_origin: str,
) -> FastAPI:
    """Create a dashboard app around one process-local manager."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()

    app = FastAPI(title="PerfRace Pair Verification Dashboard", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    def require_token(x_perfrace_token: str | None = Header(default=None)) -> None:
        if x_perfrace_token is None or not secrets.compare_digest(
            x_perfrace_token,
            access_token,
        ):
            raise HTTPException(status_code=403, detail="invalid dashboard token")

    async def accept_websocket(websocket: WebSocket) -> bool:
        origin = websocket.headers.get("origin")
        token = websocket.query_params.get("token")
        if (
            origin != allowed_origin
            or token is None
            or not secrets.compare_digest(token, access_token)
        ):
            await websocket.close(code=4403, reason="invalid dashboard origin or token")
            return False
        await websocket.accept()
        return True

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @app.get("/api/snapshot", dependencies=[Depends(require_token)])
    async def snapshot() -> dict[str, Any]:
        return manager.snapshot()

    @app.post("/api/candidates", dependencies=[Depends(require_token)])
    async def add_candidate(request: CandidateRequest) -> dict[str, int]:
        try:
            candidate_id = await manager.add_candidate({"repo_url": request.repo_url})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"id": candidate_id}

    @app.post("/api/candidates/import", dependencies=[Depends(require_token)])
    async def import_candidates(request: ImportRequest) -> dict[str, Any]:
        try:
            candidate_ids = await manager.import_jsonl(request.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ids": candidate_ids, "count": len(candidate_ids)}

    @app.post("/api/slots", dependencies=[Depends(require_token)])
    async def add_slot() -> dict[str, int]:
        return {"slotLimit": await manager.add_slot()}

    def session_workspace(session_id: str) -> Path:
        session = manager.store.session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return Path(session["workspace_path"])

    @app.get(
        "/api/sessions/{session_id}/tree",
        dependencies=[Depends(require_token)],
    )
    async def tree(session_id: str, path: str = "") -> dict[str, Any]:
        try:
            return list_directory(session_workspace(session_id), path)
        except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/api/sessions/{session_id}/file",
        dependencies=[Depends(require_token)],
    )
    async def file_preview(
        session_id: str,
        path: str,
        offset: int = 0,
        limit: int = 262_144,
    ) -> dict[str, Any]:
        try:
            payload = read_file_range(
                session_workspace(session_id),
                path,
                offset=offset,
                limit=limit,
            )
            if (
                offset == 0
                and payload["eof"]
                and not payload["binary"]
                and Path(path).suffix.lower() in MARKDOWN_SUFFIXES
            ):
                payload["renderedHtml"] = render_markdown(payload["content"])
            return payload
        except (
            ValueError,
            FileNotFoundError,
            IsADirectoryError,
            NotADirectoryError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/ws/dashboard")
    async def dashboard_socket(websocket: WebSocket) -> None:
        if not await accept_websocket(websocket):
            return
        queue = manager.subscribe()
        await websocket.send_json({"type": "snapshot", "payload": manager.snapshot()})
        receive_task = asyncio.create_task(websocket.receive_text())
        update_task = asyncio.create_task(queue.get())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {receive_task, update_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receive_task in done:
                    raw = receive_task.result()
                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        message = {}
                    if message.get("type") == "add_slot":
                        await manager.add_slot()
                    receive_task = asyncio.create_task(websocket.receive_text())
                if update_task in done:
                    await websocket.send_json(update_task.result())
                    update_task = asyncio.create_task(queue.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            manager.unsubscribe(queue)
            for task in (receive_task, update_task):
                task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await task

    @app.websocket("/ws/sessions/{session_id}/terminal")
    async def terminal_socket(
        websocket: WebSocket,
        session_id: str,
        rows: int = 0,
        cols: int = 0,
    ) -> None:
        if not await accept_websocket(websocket):
            return
        session = manager.store.session(session_id)
        if session is None:
            await websocket.close(code=4404, reason="session not found")
            return
        if not manager.tmux_exists(session["tmux_name"]):
            await websocket.close(code=4409, reason="tmux session is not running")
            return
        await attach_tmux(
            websocket,
            session["tmux_name"],
            accepted=True,
            initial_rows=rows,
            initial_cols=cols,
        )

    return app
