"""Postgres access: a small pool + the handful of queries the app needs.

SQL plano con psycopg3, sin ORM: tres tablas y queries simples no justifican
una capa de mapeo. The close() helper implements the idempotent "advance-only"
seal from propuesta-tecnica §06.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None
_MIGRATION = Path(__file__).resolve().parent / "migrations" / "0001_initial.sql"


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        # Pool size tunable per replica without a code change. At 10K/week the DB
        # isn't the bottleneck (~2-3 writes/s peak); when replica count grows past
        # ~(100 / max_size), front it with PgBouncer rather than raising this.
        max_size = int(os.getenv("DB_POOL_MAX", "10"))
        _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=max_size, open=True)
    return _pool


def init_db() -> None:
    """Apply the (idempotent) migration. Called once on startup."""
    with pool().connection() as conn:
        conn.execute(_MIGRATION.read_text("utf-8"))


# ── Conversations ───────────────────────────────────────────────────────────

def start_conversation(source: str) -> str:
    with pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO conversations (source) VALUES (%s) RETURNING id", (source,)
        ).fetchone()
    return str(row[0])


def get_conversation(cid: str) -> dict[str, Any] | None:
    with pool().connection() as conn:
        conn.row_factory = dict_row
        return conn.execute("SELECT * FROM conversations WHERE id = %s", (cid,)).fetchone()


def save_extracted(cid: str, extracted: dict[str, Any]) -> None:
    """Persist the field store after a tool call (incremental persistence).
    Mirrors full_name into candidate_name for cheap recruiter listing."""
    with pool().connection() as conn:
        conn.execute(
            "UPDATE conversations SET extracted_fields = %s, candidate_name = %s WHERE id = %s",
            (json.dumps(extracted), extracted.get("full_name"), cid),
        )


def close_conversation(
    cid: str, *, outcome: str, qualified: bool | None, reason: str | None,
    closed_by: str, summary: str | None,
) -> bool:
    """Seal the verdict. Advance-only: only an in_progress row transitions, so
    the first trigger wins and late ones are no-ops. Returns True iff we sealed it."""
    with pool().connection() as conn:
        cur = conn.execute(
            """UPDATE conversations
                  SET status='closed', outcome=%s, qualified=%s,
                      disqualification_reason=%s, closed_by=%s, summary=%s, ended_at=now()
                WHERE id=%s AND status='in_progress'""",
            (outcome, qualified, reason, closed_by, summary, cid),
        )
        return cur.rowcount == 1


# ── Turns (append-only transcript) ────────────────────────────────────────────

def append_turn(cid: str, role: str, content: str | None, tool_calls: list | None = None) -> None:
    with pool().connection() as conn:
        conn.execute(
            "INSERT INTO turns (conversation_id, role, content, tool_calls) VALUES (%s, %s, %s, %s)",
            (cid, role, content, json.dumps(tool_calls) if tool_calls else None),
        )


def get_turns(cid: str) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            "SELECT role, content, tool_calls, created_at FROM turns WHERE conversation_id=%s ORDER BY id",
            (cid,),
        ).fetchall()


def get_turns_count_any() -> int:
    """Any conversations at all? Used by the seed's idempotency guard."""
    with pool().connection() as conn:
        return conn.execute("SELECT count(*) FROM conversations").fetchone()[0]


# ── Recruiters ────────────────────────────────────────────────────────────────

def get_recruiter(username: str) -> dict[str, Any] | None:
    with pool().connection() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            "SELECT username, password_hash FROM recruiters WHERE username = %s", (username,)
        ).fetchone()


def create_recruiter(username: str, password_hash: str) -> None:
    """Idempotent: does nothing if the username already exists (for seeding)."""
    with pool().connection() as conn:
        conn.execute(
            "INSERT INTO recruiters (username, password_hash) VALUES (%s, %s) "
            "ON CONFLICT (username) DO NOTHING",
            (username, password_hash),
        )
