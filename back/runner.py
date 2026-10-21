"""Chat turn loop: one candidate message in, Rita's reply out.

The model drives: it calls tools, we run the handlers (tools.py) against the
in-memory `extracted` dict, feed results back, and loop until it replies with
text. P4a is in-memory; P5 wraps this with load-from / save-to Postgres.

Testability with zero noise: `run_turn` takes the OpenAI client as an argument
(default = the real one). Tests pass a fake; nothing else in here knows.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import guardrails
import language
from prompts import GREETING, SYSTEM_PROMPT
from tools import OPENAI_TOOL_SCHEMAS, dispatch, screening_status

_MAX_ITERS = 6  # hard cap so a misbehaving model can't loop forever


@lru_cache(maxsize=1)
def _default_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


@dataclass
class TurnResult:
    reply: str
    extracted: dict[str, Any]
    tool_calls: list[dict] = field(default_factory=list)
    completed: bool = False
    status: str = "pending"        # computed from the data, never by the model (ADR-017)
    summary: str | None = None


def _model_kwargs() -> dict[str, str]:
    # GPT-5.4 Mini by default (ADR-016); low reasoning keeps each reply fast.
    return {"model": os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini"),
            "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "low")}


def run_turn(history: list[dict], extracted: dict, *, client=None) -> TurnResult:
    """Run one user turn end to end. `history` ends with the user's message;
    `extracted` is the field store (mutated in place). An empty history gets the
    fixed greeting without a model call (ADR-012)."""
    if not history:
        return TurnResult(reply=GREETING, extracted=extracted)
    user_msg = history[-1]["content"]
    lang = language.detect(user_msg)
    result = TurnResult(reply="", extracted=extracted, status=screening_status(extracted)[0])

    # Input guardrail: block abuse/injection before spending a model call.
    if guardrails.is_blocked(user_msg):
        result.reply = guardrails.refusal(lang)
        return result

    client = client or _default_client()
    # Language-override goes last so it wins over the prompt for this turn.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "system", "content": language.override(lang)}]

    for _ in range(_MAX_ITERS):
        completion = client.chat.completions.create(
            **_model_kwargs(), messages=messages, tools=OPENAI_TOOL_SCHEMAS, tool_choice="auto"
        )
        msg = completion.choices[0].message

        if not msg.tool_calls:
            result.reply = guardrails.sanitize_output(msg.content or "")
            result.status = screening_status(extracted)[0]
            return result

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            out = dispatch(tc.function.name, extracted, args)
            result.tool_calls.append({"name": tc.function.name, "args": args, "result": out})
            if tc.function.name == "end_interview" and out.get("ok"):
                result.completed, result.summary = True, args["summary"]
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})

    result.reply = "Disculpa, tuve un problema técnico. ¿Puedes repetirlo?"
    result.status = screening_status(extracted)[0]
    return result


_NUDGE = {
    1: "El candidato lleva un rato sin responder. Hazle un recordatorio MUY breve "
       "(una frase) en su idioma, retomando la última pregunta. No saludes de nuevo. No uses herramientas.",
    2: "Segundo y último aviso. Dile en una frase, con amabilidad, que puede escribir "
       "cuando quiera y que dejas la pregunta abierta. No saludes. No uses herramientas.",
}


def run_nudge(history: list[dict], nudge_n: int, *, client=None) -> str:
    """A gentle re-engagement message after the candidate goes quiet.
    No tools, no field changes — just a short reminder in their language."""
    client = client or _default_client()
    lang = language.detect(history[-1]["content"]) if history else "es"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "system", "content": _NUDGE[nudge_n]},
                {"role": "system", "content": language.override(lang)}]
    completion = client.chat.completions.create(**_model_kwargs(), messages=messages)
    return guardrails.sanitize_output(completion.choices[0].message.content or "")
