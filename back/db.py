"""Postgres access: a small pool + the handful of queries the app needs.

SQL plano con psycopg3, sin ORM: tres tablas y queries simples no justifican
una capa de mapeo.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg import Connection, errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

if TYPE_CHECKING:
    from runner import TurnResult

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
# A chat/voice turn runs inside ONE transaction holding the row lock (ADR-024):
# lock_conversation → get_history → (agent) → save_turn. The functions below take
# that open connection; nothing is written unless the whole turn succeeds.

class Busy(Exception):
    """Another turn holds this conversation's lock."""


def start_conversation(source: str, greeting: str) -> str:
    """New conversation with Rita's fixed greeting as its first turn (ADR-012)."""
    with pool().connection() as conn:
        cid = conn.execute(
            "INSERT INTO conversations (source) VALUES (%s) RETURNING id", (source,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO turns (conversation_id, role, content) VALUES (%s, 'assistant', %s)",
            (cid, greeting),
        )
    return str(cid)


def ensure_conversation(conn: Connection, cid: UUID, greeting: str | None, source: str = "chat") -> None:
    """Create the conversation on the candidate's first contribution, so visitors who
    never write or speak leave no row. Inside the turn's transaction: a failed turn leaves nothing."""
    created = conn.execute(
        "INSERT INTO conversations (id, source) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING", (cid, source)
    ).rowcount
    if created and greeting:
        conn.execute(
            "INSERT INTO turns (conversation_id, role, content) VALUES (%s, 'assistant', %s)",
            (cid, greeting),
        )


def lock_conversation(conn: Connection, cid: UUID) -> dict[str, Any] | None:
    """The conversation row, locked until the transaction ends. None if it doesn't
    exist; Busy if another turn holds it (we fail fast instead of queueing)."""
    try:
        return conn.cursor(row_factory=dict_row).execute(
            "SELECT * FROM conversations WHERE id = %s FOR UPDATE NOWAIT", (cid,)
        ).fetchone()
    except errors.LockNotAvailable as e:
        raise Busy from e


def get_history(conn: Connection, cid: UUID) -> list[dict[str, str]]:
    """The transcript as the model sees it: text only, tools left out (ADR-025)."""
    return conn.cursor(row_factory=dict_row).execute(
        "SELECT role, content FROM turns WHERE conversation_id = %s ORDER BY id", (cid,)
    ).fetchall()


def save_turn(conn: Connection, cid: UUID, message: str, result: TurnResult) -> None:
    """The candidate's message, Rita's reply with the tools it ran, and the data +
    status after the turn. A candidate message resets the nudge count (ADR-026)
    and reopens a closed interview unless Rita closes it again now (ADR-028)."""
    conn.execute(
        "INSERT INTO turns (conversation_id, role, content) VALUES (%s, 'user', %s)", (cid, message)
    )
    conn.execute(
        "INSERT INTO turns (conversation_id, role, content, tool_calls) "
        "VALUES (%s, 'assistant', %s, %s)",
        (cid, result.reply, json.dumps(result.tool_calls) if result.tool_calls else None),
    )
    conn.execute(
        """UPDATE conversations
              SET extracted_fields = %s, candidate_name = %s, screening_status = %s,
                  knockout_reason = %s, completed = %s, summary = COALESCE(%s, summary),
                  sentiment = COALESCE(%s, sentiment), nudge_count = 0, last_activity_at = now()
            WHERE id = %s""",
        (json.dumps(result.extracted), result.extracted.get("full_name"), result.status,
         result.knockout, result.completed, result.summary, result.sentiment, cid),
    )


def save_nudge(conn: Connection, cid: UUID, reply: str) -> None:
    """Rita's reminder after a silence. Not candidate activity: last_activity_at stays."""
    conn.execute(
        "INSERT INTO turns (conversation_id, role, content) VALUES (%s, 'assistant', %s)", (cid, reply)
    )
    conn.execute("UPDATE conversations SET nudge_count = nudge_count + 1 WHERE id = %s", (cid,))


# ── Voice: the browser relays each tool call and each finished sentence ─────────

def save_voice_data(conn: Connection, cid: UUID, extracted: dict, status: str,
                    knockout: str | None, *, completed: bool, summary: str | None,
                    sentiment: str | None) -> None:
    """Data + status after a voice tool call. Once Rita closes the call it stays
    closed (unlike chat, a call has no "new message" that reopens it)."""
    conn.execute(
        """UPDATE conversations
              SET extracted_fields = %s, candidate_name = %s, screening_status = %s,
                  knockout_reason = %s, completed = %s, summary = COALESCE(%s, summary),
                  sentiment = COALESCE(%s, sentiment), last_activity_at = now()
            WHERE id = %s""",
        (json.dumps(extracted), extracted.get("full_name"), status, knockout, completed, summary, sentiment, cid),
    )


def save_voice_turns(conn: Connection, cid: UUID, turns: list[tuple[str, str]]) -> None:
    """Transcribed sentences, in order. A candidate sentence is activity; Rita's isn't."""
    for role, text in turns:
        conn.execute(
            "INSERT INTO turns (conversation_id, role, content) VALUES (%s, %s, %s)", (cid, role, text)
        )
    if any(role == "user" for role, _ in turns):
        conn.execute("UPDATE conversations SET last_activity_at = now() WHERE id = %s", (cid,))


def get_conversation(cid: str) -> dict[str, Any] | None:
    with pool().connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            "SELECT * FROM conversations WHERE id = %s", (cid,)
        ).fetchone()


# ── Recruiter panel ───────────────────────────────────────────────────────────

# "inactive" is derived, never stored (ADR-018): open and quiet for idle minutes.
_LISTING = """id, candidate_name, source, screening_status, knockout_reason, completed,
    NOT completed AND last_activity_at < now() - make_interval(mins => %(idle)s) AS inactive,
    created_at, last_activity_at"""


def list_conversations(idle_minutes: int) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            f"SELECT {_LISTING} FROM conversations ORDER BY last_activity_at DESC",
            {"idle": idle_minutes},
        ).fetchall()


def get_conversation_detail(cid: UUID, idle_minutes: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            f"SELECT {_LISTING}, extracted_fields, summary, sentiment FROM conversations WHERE id = %(id)s",
            {"idle": idle_minutes, "id": cid},
        ).fetchone()


# ── Turns (append-only transcript) ────────────────────────────────────────────

def get_turns(cid: str) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
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
        return conn.cursor(row_factory=dict_row).execute(
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
