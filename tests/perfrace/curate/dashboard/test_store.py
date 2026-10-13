from __future__ import annotations

import pytest

from perfrace.curate.dashboard.store import DashboardStore


def test_import_jsonl_preserves_order_and_extra_fields(tmp_path) -> None:
    store = DashboardStore(tmp_path / "state.db")

    ids = store.import_jsonl(
        "\n".join(
            [
                '{"repo_url":"https://github.com/a/one","score":1}',
                '{"repo_url":"https://github.com/b/two","source":"queue"}',
            ]
        )
    )

    queued = store.queued_candidates()
    assert ids == [1, 2]
    assert [item["repo_url"] for item in queued] == [
        "https://github.com/a/one",
        "https://github.com/b/two",
    ]
    assert queued[0]["payload"]["score"] == 1


def test_importing_identical_jsonl_is_idempotent(tmp_path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    content = '{"repo_url":"https://github.com/a/one"}\n'

    assert store.import_jsonl(content) == [1]
    assert store.import_jsonl(content) == []
    assert len(store.queued_candidates()) == 1


def test_invalid_jsonl_does_not_leave_partial_candidates(tmp_path) -> None:
    store = DashboardStore(tmp_path / "state.db")

    with pytest.raises(ValueError, match="line 2"):
        store.import_jsonl('{"repo_url":"https://github.com/a/one"}\n{"missing":"repo"}\n')

    assert store.queued_candidates() == []


def test_upsert_session_assigns_candidate_and_updates_state(tmp_path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    candidate_id = store.add_candidate({"repo_url": "https://github.com/a/one"})
    values = {
        "session_id": "session-1",
        "candidate_id": candidate_id,
        "repo_url": "https://github.com/a/one",
        "model": "gpt-5.6-sol",
        "state": "running",
        "stage": "Explore & Design",
        "engagement_kind": None,
        "engagement_reason": None,
        "started_at": "2026-08-29T00:00:00Z",
        "disposition": None,
        "tmux_name": "perfrace-pv-session-1",
        "session_dir": "/tmp/session-1",
        "workspace_path": "/tmp/staging/session-1",
        "instance_path": None,
        "live_cost_usd": 0.0,
        "human_comments": 0,
        "error": None,
    }

    store.upsert_session(values)
    store.update_session("session-1", state="needs_human", human_comments=2)

    assert store.queued_candidates() == []
    session = store.session("session-1")
    assert session is not None
    assert session["state"] == "needs_human"
    assert session["human_comments"] == 2


def test_candidate_claim_is_atomic_and_recoverable(tmp_path) -> None:
    store = DashboardStore(tmp_path / "state.db")
    candidate_id = store.add_candidate({"repo_url": "https://github.com/a/one"})

    assert store.claim_candidate(candidate_id, "session-1") is True
    assert store.claim_candidate(candidate_id, "session-2") is False
    assert store.queued_candidates() == []
    assert store.candidate_id_for_session("session-1") == candidate_id
    assert store.claimed_candidates_without_session()[0]["session_id"] == "session-1"

    store.release_candidate_claim(candidate_id, "session-2")
    assert store.queued_candidates() == []
    store.release_candidate_claim(candidate_id, "session-1")
    assert [item["id"] for item in store.queued_candidates()] == [candidate_id]
