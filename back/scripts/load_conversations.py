"""Load simulated conversations into the database, so they show up in the recruiter panel.

Run:  DATABASE_URL=... uv run python -m scripts.load_conversations simulaciones.json marta javier ...
Each one goes through the real save path (save_turn). Skips a candidate whose name is
already in the database, so running it twice doesn't duplicate anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.prompts import GREETING
from agent.runner import TurnResult
from agent.tools import screening_status
from storage import db


def load(run: dict) -> bool:
    final = run["extracted"]
    with db.pool().connection() as conn:
        if conn.execute("SELECT 1 FROM conversations WHERE candidate_name = %s",
                        (final.get("full_name"),)).fetchone():
            return False
    cid = db.start_conversation("chat", GREETING)
    status, knockout = screening_status(final)
    closing = next((t["args"] for t in run["transcript"][-1]["tools"] if t["name"] == "end_interview"), {})
    with db.pool().connection() as conn:
        for n, turn in enumerate(run["transcript"], 1):
            last = n == len(run["transcript"])
            db.save_turn(conn, cid, turn["candidato"], TurnResult(
                reply=turn["rita"], extracted=final, tool_calls=turn["tools"], status=status,
                knockout=knockout, completed=last and run["completed"],
                summary=closing.get("summary") if last else None,
                sentiment=closing.get("sentiment") if last else None))
    return True


def main() -> None:
    runs = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    db.init_db()
    for name in sys.argv[2:]:
        print(f"{name:<8} {'cargada' if load(runs[name]) else 'ya estaba, se omite'}")


if __name__ == "__main__":
    main()
