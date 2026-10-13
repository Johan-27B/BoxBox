"""SQLite persistence for dashboard candidates and sessions."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_candidate_jsonl(content: str) -> list[dict[str, Any]]:
    """Parse candidate JSONL while requiring only ``repo_url``."""
    payloads: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"candidate on line {line_number} must be a JSON object")
        repo_url = payload.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url.strip():
            raise ValueError(f"line {line_number}: candidate must include a non-empty repo_url")
        payloads.append(payload)
    return payloads


class DashboardStore:
    """Persist queue order and recoverable session metadata."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_url TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    queue_order INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    session_id TEXT UNIQUE
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    candidate_id INTEGER,
                    repo_url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    state TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    engagement_kind TEXT,
                    engagement_reason TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    disposition TEXT,
                    tmux_name TEXT NOT NULL,
                    session_dir TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    instance_path TEXT,
                    live_cost_usd REAL,
                    human_comments INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(id)
                );

                CREATE TABLE IF NOT EXISTS imports (
                    content_hash TEXT PRIMARY KEY,
                    imported_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS sessions_candidate_id_unique
                ON sessions(candidate_id)
                WHERE candidate_id IS NOT NULL;
                """
            )

    def add_candidate(self, payload: dict[str, Any]) -> int:
        repo_url = payload.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url.strip():
            raise ValueError("candidate JSON must include a non-empty repo_url")
        with self._connect() as connection:
            queue_order = connection.execute(
                "SELECT COALESCE(MAX(queue_order), 0) + 1 FROM candidates"
            ).fetchone()[0]
            cursor = connection.execute(
                """
                INSERT INTO candidates
                    (repo_url, payload_json, queue_order, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    repo_url.strip(),
                    json.dumps(payload, sort_keys=True),
                    queue_order,
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def import_jsonl(self, content: str) -> list[int]:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM imports WHERE content_hash = ?",
                (content_hash,),
            ).fetchone():
                return []
        candidate_ids: list[int] = []
        payloads = parse_candidate_jsonl(content)
        try:
            for payload in payloads:
                candidate_ids.append(self.add_candidate(payload))
        except Exception:
            with self._connect() as connection:
                if candidate_ids:
                    placeholders = ",".join("?" for _ in candidate_ids)
                    connection.execute(
                        f"DELETE FROM candidates WHERE id IN ({placeholders})",
                        candidate_ids,
                    )
            raise
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO imports (content_hash, imported_at) VALUES (?, ?)",
                (content_hash, utc_now()),
            )
        return candidate_ids

    def queued_candidates(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, repo_url, payload_json, queue_order, created_at
                FROM candidates
                WHERE session_id IS NULL
                ORDER BY queue_order
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "repo_url": row["repo_url"],
                "payload": json.loads(row["payload_json"]),
                "queue_order": row["queue_order"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def claim_candidate(self, candidate_id: int, session_id: str) -> bool:
        """Atomically reserve one queued candidate for a session UUID."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE candidates
                SET session_id = ?
                WHERE id = ? AND session_id IS NULL
                """,
                (session_id, candidate_id),
            )
            return cursor.rowcount == 1

    def release_candidate_claim(self, candidate_id: int, session_id: str) -> None:
        """Release a claim only when it still belongs to the expected session."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE candidates
                SET session_id = NULL
                WHERE id = ? AND session_id = ?
                """,
                (candidate_id, session_id),
            )

    def candidate_id_for_session(self, session_id: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM candidates WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def claimed_candidates_without_session(self) -> list[dict[str, Any]]:
        """Return durable claims whose dashboard session row is not written yet."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT candidates.id, candidates.repo_url, candidates.payload_json,
                       candidates.queue_order, candidates.created_at,
                       candidates.session_id
                FROM candidates
                LEFT JOIN sessions
                    ON sessions.session_id = candidates.session_id
                WHERE candidates.session_id IS NOT NULL
                  AND sessions.session_id IS NULL
                ORDER BY candidates.queue_order
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "repo_url": row["repo_url"],
                "payload": json.loads(row["payload_json"]),
                "queue_order": row["queue_order"],
                "created_at": row["created_at"],
                "session_id": row["session_id"],
            }
            for row in rows
        ]

    def upsert_session(self, values: dict[str, Any]) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, candidate_id, repo_url, model, state, stage,
                    engagement_kind, engagement_reason, started_at, updated_at,
                    disposition, tmux_name, session_dir, workspace_path,
                    instance_path, live_cost_usd, human_comments, error
                ) VALUES (
                    :session_id, :candidate_id, :repo_url, :model, :state, :stage,
                    :engagement_kind, :engagement_reason, :started_at, :updated_at,
                    :disposition, :tmux_name, :session_dir, :workspace_path,
                    :instance_path, :live_cost_usd, :human_comments, :error
                )
                ON CONFLICT(session_id) DO UPDATE SET
                    candidate_id=excluded.candidate_id,
                    repo_url=excluded.repo_url,
                    model=excluded.model,
                    state=excluded.state,
                    stage=excluded.stage,
                    engagement_kind=excluded.engagement_kind,
                    engagement_reason=excluded.engagement_reason,
                    updated_at=excluded.updated_at,
                    disposition=excluded.disposition,
                    tmux_name=excluded.tmux_name,
                    session_dir=excluded.session_dir,
                    workspace_path=excluded.workspace_path,
                    instance_path=excluded.instance_path,
                    live_cost_usd=excluded.live_cost_usd,
                    human_comments=excluded.human_comments,
                    error=excluded.error
                """,
                {**values, "updated_at": now},
            )
            candidate_id = values.get("candidate_id")
            if candidate_id is not None:
                cursor = connection.execute(
                    """
                    UPDATE candidates
                    SET session_id = ?
                    WHERE id = ? AND (session_id IS NULL OR session_id = ?)
                    """,
                    (values["session_id"], candidate_id, values["session_id"]),
                )
                if cursor.rowcount != 1:
                    raise ValueError(f"candidate {candidate_id} is already claimed")

    def update_session(self, session_id: str, **changes: Any) -> None:
        if not changes:
            return
        changes["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in changes)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE sessions SET {assignments} WHERE session_id = :session_id",
                {"session_id": session_id, **changes},
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown dashboard session: {session_id}")

    def sessions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sessions.*, candidates.payload_json
                FROM sessions
                LEFT JOIN candidates ON candidates.id = sessions.candidate_id
                """
            ).fetchall()
        return [
            {
                **dict(row),
                "candidate": (json.loads(row["payload_json"]) if row["payload_json"] else None),
            }
            for row in rows
        ]

    def session(self, session_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self.sessions() if row["session_id"] == session_id),
            None,
        )
