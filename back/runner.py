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
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from prompts import SYSTEM_PROMPT
from tools import OPENAI_TOOL_SCHEMAS, dispatch, recompute_qualified

_MAX_ITERS = 6  # hard cap so a misbehaving model can't loop forever
# Catch a model that narrates the close as text instead of calling the tool.
_NARRATED = re.compile(r"complete_screening\s*\(", re.IGNORECASE)


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
    qualified: bool | None = None


def run_turn(history: list[dict], extracted: dict, *, client=None) -> TurnResult:
    """Run one user turn end to end. `history` ends with the user's message;
    `extracted` is the field store (mutated in place)."""
    client = client or _default_client()
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    result = TurnResult(reply="", extracted=extracted)

    for _ in range(_MAX_ITERS):
        completion = client.chat.completions.create(
            model=model, messages=messages, tools=OPENAI_TOOL_SCHEMAS, tool_choice="auto"
        )
        msg = completion.choices[0].message

        if not msg.tool_calls:
            result.reply = msg.content or ""
            # Safety net: model narrated the close instead of calling it.
            if not result.completed and _NARRATED.search(result.reply):
                _finish(result, {"summary": result.reply})
                result.reply = _NARRATED.sub("", result.reply).strip()
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
            if tc.function.name == "complete_screening" and out.get("ok"):
                _finish(result, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})

    result.reply = "Disculpa, tuve un problema técnico. ¿Puedes repetirlo?"
    return result


def _finish(result: TurnResult, args: dict) -> None:
    """Seal the verdict in Python (the safety net, ADR-002)."""
    result.completed = True
    result.qualified = recompute_qualified(result.extracted)
