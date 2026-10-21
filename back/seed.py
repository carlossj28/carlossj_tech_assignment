"""Seed a demo recruiter + demo conversations so the dashboard has something to show.

Run: `uv run python -m seed`. Idempotent: skips conversations if any exist,
and the recruiter upsert is a no-op if the username is taken.
"""
from __future__ import annotations

import os

import auth
import db

_DEMO = [
    dict(source="chat", outcome="qualified", qualified=True, closed_by="confirm",
         name="Marta Gil",
         fields={"full_name": "Marta Gil", "has_driver_license": True, "city": "Madrid / Arganzuela",
                 "availability": ["full_time"], "preferred_schedule": ["morning"],
                 "prior_experience": {"years": 2, "platforms": ["Glovo"]}, "start_date": "2026-11-03"},
         summary="Repartidora con coche y 2 años en Glovo; Madrid Arganzuela; jornada completa.",
         turns=[("assistant", "¡Hola! Soy Rita 👋 ¿Cómo te llamas?"),
                ("user", "Marta, tengo coche y vivo en Arganzuela")]),
    dict(source="chat", outcome="disqualified", qualified=False, reason="no_license", closed_by="confirm",
         name="Jorge Ruiz",
         fields={"full_name": "Jorge Ruiz", "has_driver_license": False},
         summary="Sin carné de conducir; descartado.",
         turns=[("assistant", "¿Tienes carné de conducir?"), ("user", "No, todavía no")]),
    dict(source="voice", outcome="review", qualified=None, closed_by="hangup",
         name="Elena Sanz",
         fields={"full_name": "Elena Sanz", "has_driver_license": True, "city": "Ciudad de México / Coyoacán"},
         summary="Colgó antes de confirmar; datos completos pendientes de revisión.",
         turns=[("assistant", "¿En qué zona te gustaría trabajar?"), ("user", "En Coyoacán")]),
]


def run() -> None:
    db.init_db()

    # Demo recruiter (upsert is a no-op if it already exists).
    user = os.getenv("RECRUITER_DEMO_USER", "demo")
    pwd = os.getenv("RECRUITER_DEMO_PASSWORD", "demo")
    db.create_recruiter(user, auth.hash_password(pwd))
    print(f"recruiter '{user}' ready")

    if db.get_turns_count_any():
        print("demo conversations already present, skipping")
        return
    for d in _DEMO:
        cid = db.start_conversation(d["source"])
        db.save_extracted(cid, d["fields"])
        for role, content in d["turns"]:
            db.append_turn(cid, role, content)
        db.close_conversation(
            cid, outcome=d["outcome"], qualified=d["qualified"],
            reason=d.get("reason"), closed_by=d["closed_by"], summary=d["summary"],
        )
    print(f"seeded {len(_DEMO)} demo conversations")


if __name__ == "__main__":
    run()
