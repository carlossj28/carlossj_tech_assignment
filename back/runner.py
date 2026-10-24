"""Chat turn loop: one candidate message in, Rita's reply out.

The model drives: it calls tools, we run the handlers (tools.py) against the
in-memory `extracted` dict, feed results back, and loop until it replies with
text. Stateless: chat.py loads history + data from Postgres and saves the result.

Testability with zero noise: `run_turn` takes the OpenAI client as an argument
(default = the real one). Tests pass a fake; nothing else in here knows.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

import guardrails
import language
from prompts import GREETING, SYSTEM_PROMPT, TECH_ERROR
from tools import OPENAI_TOOL_SCHEMAS, dispatch, screening_status

_MAX_ITERS = 6  # hard cap so a misbehaving model can't loop forever
# A second save in one turn was always the model filling the next field of the flow on
# its own (evals: a city or a license nobody gave). One message = one save_answer call.
_SECOND_SAVE = {"ok": False, "validation_error": "already saved this message: save only "
                "what the candidate said, all in one call"}
# A knock-out this turn must leave the interview closed; if Rita says goodbye without
# end_interview (evals: ~1 in 3 on a calm out-of-area candidate), she is asked once more.
_CLOSE_NOW = ("Acabas de despedirte por un knockout sin llamar a end_interview. Llámala ahora "
              "con el resumen y el tono; no escribas otra despedida.")


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
    knockout: str | None = None
    summary: str | None = None
    sentiment: str | None = None   # the candidate's tone, set by Rita on close


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
    result = TurnResult(reply="", extracted=extracted)
    result.status, result.knockout = screening_status(extracted)

    # Input guardrail: block abuse/injection before spending a model call.
    if guardrails.is_blocked(user_msg):
        result.reply = guardrails.refusal(lang)
        return result

    client = client or _default_client()
    # Text-only history + what is already saved (ADR-025); the language override
    # goes last so it wins over the prompt for this turn.
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": _saved_data(extracted)}, *history,
                {"role": "system", "content": language.override(lang)}]

    saved, knockout_before, farewell = False, result.knockout, None
    for _ in range(_MAX_ITERS):
        completion = client.chat.completions.create(
            **_model_kwargs(), messages=messages, tools=OPENAI_TOOL_SCHEMAS, tool_choice="auto"
        )
        msg = completion.choices[0].message

        if not msg.tool_calls:
            result.status, result.knockout = screening_status(extracted)
            if result.knockout not in (None, knockout_before) and not result.completed and not farewell:
                farewell = guardrails.sanitize_output(msg.content or "")
                messages += [{"role": "assistant", "content": msg.content or ""},
                             {"role": "system", "content": _CLOSE_NOW}]
                continue
            result.reply = farewell or guardrails.sanitize_output(msg.content or "")
            return result

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
                if tc.function.name == "save_answer" and saved:
                    out = _SECOND_SAVE
                else:
                    out = dispatch(tc.function.name, extracted, args)
            except json.JSONDecodeError:  # model sent broken JSON: tell it, don't crash the turn
                args, out = {}, {"ok": False, "validation_error": "arguments are not valid JSON"}
            saved = saved or (tc.function.name == "save_answer" and out.get("ok") is True)
            result.tool_calls.append({"name": tc.function.name, "args": args, "result": out})
            if tc.function.name == "end_interview" and out.get("ok"):
                result.completed, result.summary, result.sentiment = True, args["summary"], args["sentiment"]
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})

    result.reply = farewell or TECH_ERROR
    result.status, result.knockout = screening_status(extracted)
    return result


_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _saved_data(extracted: dict) -> str:
    # Today's date too: without it "el lunes que viene" can't become a start_date (evals).
    today = date.today()
    return (f"Hoy es {_WEEKDAYS[today.weekday()]} {today.isoformat()}. "
            "Datos ya guardados de este candidato (no los vuelvas a preguntar): " + (
                json.dumps(extracted, ensure_ascii=False) if extracted else "ninguno todavía"))


_NUDGE = {  # up to 3 per silence (ADR-026)
    1: "El candidato lleva un rato sin responder. Hazle un recordatorio MUY breve "
       "(una frase) en su idioma, retomando la última pregunta. No saludes de nuevo. No uses herramientas.",
    2: "Sigue sin responder. Retoma la última pregunta en una frase, con otras palabras "
       "que el recordatorio anterior. No saludes. No uses herramientas.",
    3: "Último aviso. Dile en una frase, con amabilidad, que puede escribir "
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
