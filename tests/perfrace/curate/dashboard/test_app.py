from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from perfrace.curate.dashboard.app import create_app
from perfrace.curate.dashboard.store import DashboardStore


class FakeManager:
    def __init__(self, store: DashboardStore):
        self.store = store
        self.slot_limit = 4
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    def snapshot(self):
        return {"slotLimit": self.slot_limit, "sessions": [], "queue": []}

    async def add_candidate(self, payload):
        return self.store.add_candidate(payload)

    async def import_jsonl(self, content):
        return self.store.import_jsonl(content)

    async def add_slot(self):
        self.slot_limit += 1
        return self.slot_limit

    def subscribe(self):
        return asyncio.Queue()

    def unsubscribe(self, _queue):
        return None

    @staticmethod
    def tmux_exists(_name):
        return False


def _session(workspace: Path) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "candidate_id": None,
        "repo_url": "https://github.com/example/project",
        "model": "gpt-5.6-sol",
        "state": "running",
        "stage": "Explore & Design",
        "engagement_kind": None,
        "engagement_reason": None,
        "started_at": "2026-08-29T00:00:00Z",
        "disposition": None,
        "tmux_name": "perfrace-pv-session-1",
        "session_dir": str(workspace.parent),
        "workspace_path": str(workspace),
        "instance_path": None,
        "live_cost_usd": 0.0,
        "human_comments": 0,
        "error": None,
    }


def test_rest_api_manages_candidates_slots_and_files(tmp_path: Path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "instruction.md").write_text("Optimize this project.\n")
    store.upsert_session(_session(workspace))
    manager = FakeManager(store)

    headers = {"X-PerfRace-Token": "test-token"}
    with TestClient(
        create_app(
            manager,
            access_token="test-token",
            allowed_origin="http://testserver",
        )
    ) as client:
        assert client.get("/api/snapshot").status_code == 403
        assert client.get("/api/snapshot", headers=headers).json()["slotLimit"] == 4
        assert (
            client.post(
                "/api/candidates",
                json={"repo_url": "https://github.com/a/one"},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/candidates/import",
                json={"content": '{"repo_url":"https://github.com/b/two"}\n'},
                headers=headers,
            ).json()["count"]
            == 1
        )
        assert client.post("/api/slots", headers=headers).json()["slotLimit"] == 5

        tree = client.get("/api/sessions/session-1/tree", headers=headers).json()
        assert tree["entries"][0]["name"] == "instruction.md"
        preview = client.get(
            "/api/sessions/session-1/file",
            params={"path": "instruction.md"},
            headers=headers,
        ).json()
        assert preview["content"] == "Optimize this project.\n"
        assert preview["renderedHtml"] == "<p>Optimize this project.</p>\n"
        assert (
            client.get(
                "/api/sessions/session-1/file",
                params={"path": "../secret"},
                headers=headers,
            ).status_code
            == 400
        )

        with client.websocket_connect(
            "/ws/dashboard?token=test-token",
            headers={"origin": "http://testserver"},
        ) as websocket:
            assert websocket.receive_json()["type"] == "snapshot"

        try:
            with client.websocket_connect(
                "/ws/dashboard?token=test-token",
                headers={"origin": "http://malicious.example"},
            ):
                raise AssertionError("cross-origin WebSocket was accepted")
        except WebSocketDisconnect as exc:
            assert exc.code == 4403
