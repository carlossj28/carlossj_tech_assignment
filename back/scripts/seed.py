"""Seed a demo recruiter + demo conversations so the dashboard has something to show.

Run: `uv run python -m scripts.seed`. Idempotent: skips conversations if any exist,
and the recruiter upsert is a no-op if the username is taken.
"""
from __future__ import annotations

import os

from agent.runner import TurnResult
from agent.tools import screening_status
from api import auth
from storage import db

_DEMO = [  # one exchange each, written through the real save path
    dict(source="chat", rita="¿Tienes carné de conducir y en qué ciudad vives?",
         user="Sí, desde noviembre. Vivo en Madrid", reply="¡Genial! Ya lo tengo todo. ¡Gracias, Marta!",
         fields={"full_name": "Marta Gil", "has_driver_license": True, "city": "Madrid",
                 "availability": ["full_time"], "preferred_schedule": ["morning"],
                 "prior_experience": {"years": 2, "platforms": ["Glovo"]}, "start_date": "2026-11-03"},
         completed=True, summary="Repartidora con 2 años en Glovo; Madrid; jornada completa.",
         sentiment="positive"),
    dict(source="chat", rita="¿Tienes carné de conducir?", user="No. Es la tercera oferta que me lo pide, qué rollo",
         reply="Gracias, Jorge. Para este puesto el carné es imprescindible.",
         fields={"full_name": "Jorge Ruiz", "has_driver_license": False},
         completed=True, summary="Sin carné de conducir; descartado. Se quejó del requisito.",
         sentiment="frustrated"),
    dict(source="voice", rita="¿En qué ciudad te gustaría trabajar?", user="En Ciudad de México",
         reply="¡Perfecto! ¿Qué disponibilidad tienes?",
         fields={"full_name": "Elena Sanz", "has_driver_license": True, "city": "Ciudad de México"},
         completed=False, summary=None, sentiment=None),  # hung up mid-call: qualified but inactive
]


def run() -> None:
    user, pwd = os.getenv("RECRUITER_DEMO_USER"), os.getenv("RECRUITER_DEMO_PASSWORD")
    if not user or not pwd:  # no default credentials: they would end up in a client env
        raise SystemExit("set RECRUITER_DEMO_USER and RECRUITER_DEMO_PASSWORD")
    db.init_db()

    # Demo recruiter (upsert is a no-op if it already exists).
    db.create_recruiter(user, auth.hash_password(pwd))
    print(f"recruiter '{user}' ready")

    if db.get_turns_count_any():
        print("demo conversations already present, skipping")
        return
    for d in _DEMO:  # same write path as a real turn
        cid = db.start_conversation(d["source"], d["rita"])
        status, knockout = screening_status(d["fields"])
        result = TurnResult(reply=d["reply"], extracted=d["fields"], completed=d["completed"],
                            status=status, knockout=knockout, summary=d["summary"],
                            sentiment=d["sentiment"])
        with db.pool().connection() as conn:
            db.save_turn(conn, cid, d["user"], result)
    print(f"seeded {len(_DEMO)} demo conversations")


if __name__ == "__main__":
    run()
