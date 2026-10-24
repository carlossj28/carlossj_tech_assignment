"""LLM evals: scripted candidates against the real agent (run_turn).

Each case is a fixed list of candidate messages; some turns carry expectations
checked right after Rita answers. We check data, never wording: saved fields,
status, knock-out, completed, reply language. So prompt changes (FAQ, tone,
summary format) don't break the evals unless they break the screening itself.

Scripted, not LLM-simulated, candidates: reproducible, cheap, one model in the
loop. Cases and what each one covers: cases.json + README.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import language
from runner import run_turn
from tools import _PARTS, INTERVIEW_KEY

CASES = Path(__file__).resolve().parent / "cases.json"


def load_cases() -> list[dict]:
    return json.loads(CASES.read_text("utf-8"))


@dataclass
class CaseResult:
    id: str
    failures: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures and self.error is None


def _norm(v: Any) -> Any:
    """Compare loosely where the model may vary harmlessly: case, spacing, list order."""
    if isinstance(v, str):
        return " ".join(v.casefold().split())
    if isinstance(v, list):
        return sorted((_norm(x) for x in v), key=repr)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def check(expect: dict, extracted: dict, r) -> list[str]:
    """Failures (empty = pass) of one turn's expectations against the agent's state."""
    fails = []
    for k, want in expect.get("saved", {}).items():
        if _norm(extracted.get(k)) != _norm(want):
            fails.append(f"{k}: esperado {want!r}, guardado {extracted.get(k)!r}")
    fails += [f"{k}: no debería estar guardado ({extracted[k]!r})"
              for k in expect.get("not_saved", []) if k in extracted]
    fails += [f"{k}: debería estar guardado" for k in expect.get("present", []) if k not in extracted]
    for key, got in (("status", r.status), ("knockout", r.knockout), ("completed", r.completed)):
        if key in expect and expect[key] != got:
            fails.append(f"{key}: esperado {expect[key]!r}, obtenido {got!r}")
    if "reply_lang" in expect and language.detect(r.reply) != expect["reply_lang"]:
        fails.append(f"idioma de la respuesta: esperado {expect['reply_lang']}")
    if "booked" in expect and (INTERVIEW_KEY in extracted) != expect["booked"]:
        fails.append(f"entrevista reservada: esperado {expect['booked']}")
    if "slot_part" in expect:
        slot = extracted.get(INTERVIEW_KEY)
        lo, hi = _PARTS[expect["slot_part"]]
        if not slot or not lo <= int(slot[11:13]) < hi:
            fails.append(f"hora de la entrevista: esperado {expect['slot_part']}, reservado {slot!r}")
    return fails


def run_case(case: dict, *, client=None) -> CaseResult:
    """Play one scripted candidate through run_turn, like chat.py does (no DB)."""
    res = CaseResult(id=case["id"])
    history: list[dict] = [{"role": "assistant", "content": run_turn([], {}).reply}]  # greeting
    try:
        for n, turn in enumerate(case["turns"], 1):
            history.append({"role": "user", "content": turn["say"]})
            r = run_turn(history, res.extracted, client=client)
            history.append({"role": "assistant", "content": r.reply})
            res.transcript.append({"candidato": turn["say"], "rita": r.reply,
                                   "tools": r.tool_calls, "status": r.status})
            res.failures += [f"turno {n}: {f}" for f in check(turn.get("expect", {}), res.extracted, r)]
    except Exception as e:  # an API error fails this case, not the whole run
        res.error = f"{type(e).__name__}: {e}"
    return res
