"""Candidate voice: the browser talks to OpenAI Realtime over WebRTC and relays to us
what must be stored. We mint the short-lived key it connects with (ADR-007: our key
never reaches it), run the model's tool calls, and keep the transcript.

Same brain as chat: same prompt, same tools, same status computed in Python. The
conversation is created by the candidate's first contribution, never by Rita.
"""
from __future__ import annotations

import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.prompts import SYSTEM_PROMPT, TECH_ERROR
from agent.runner import _default_client
from agent.tools import OPENAI_TOOL_SCHEMAS, dispatch, screening_status
from api.chat import _turn
from storage import db

router = APIRouter(prefix="/api/voice")

_VOICE_RULES = ("\n# Voz\nEstás en una llamada: frases habladas y cortas, sin emojis, listas ni formato. "
                # The chat greets with fixed text (ADR-012); a call can't, so these are its must-says.
                "Empieza presentándote como Rita, la asistente virtual de Grupo Sazón: unas preguntas "
                "rápidas (unos 3 minutos) para el puesto de repartidor, y sus respuestas solo se usan "
                "para este proceso. Luego pregunta su nombre.\n"
                # The voice model tends to say it saves instead of saving (a real call: 0/7 stored).
                "Cuando el candidato te dé un dato, llama a save_answer antes de contestarle. Nunca "
                "digas que lo apuntas sin llamarla, y no le digas que no encaja hasta que save_answer "
                "devuelva knockout.\n"
                # The browser hangs up after the goodbye that follows end_interview, so
                # corrections must come before it (ADR-029).
                "Antes de llamar a end_interview (también tras un knockout, y después de agendar si es "
                "qualified), pregunta siempre "
                "«¿Puedo ayudarte en algo más?». Si pide un cambio, guárdalo y vuelve a preguntarlo. "
                "Llama a end_interview solo cuando diga que no; después despídete en una frase: "
                "la llamada se cuelga sola.\n"
                # A call has no writing to judge the variant by, and the first question is the licence:
                # until Rita knows, a term that fits both countries.
                "Escucha cómo habla desde su primera frase: si suena a México («qué onda», «pues» al "
                "final, «mande»…), usa español de México desde ese momento. Si aún no lo sabes, pregunta "
                "por el «carné o licencia de conducir».\n"
                # A call isn't a screen: reading 12 cities is slow, and "escríbeme" makes no sense.
                "Al preguntar la ciudad, no leas la lista: pregunta solo en qué ciudad está.\n"
                "Tras un knockout (por carné o por ciudad), en voz no cierres en ese mismo turno: explica "
                "el motivo, di «si me he equivocado, dímelo» (nunca «escríbeme»: es una llamada) y "
                "pregunta «¿Puedo ayudarte en algo más?». Solo si es por ciudad, nombra las ciudades "
                "cubiertas de su país (España o México) en una frase natural.\n"
                # Only voice can see this: the browser turns a failed call to the back into `error`.
                "Si una herramienta devuelve error (no validation_error), es un problema técnico "
                f"guardando los datos: díselo con naturalidad, más o menos así: \"{TECH_ERROR}\", "
                "y despídete con amabilidad.")

# Realtime takes the same tools, flattened: {"type", "name", ...} instead of {"type", "function": {...}}.
_TOOLS = [{"type": "function", **t["function"]} for t in OPENAI_TOOL_SCHEMAS]


class ToolBody(BaseModel):
    conversation_id: UUID
    name: str
    args: dict


class Sentence(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=2000)


class TranscriptBody(BaseModel):
    conversation_id: UUID
    # Rita speaks first; the browser holds her sentences and sends them with the
    # candidate's first one, so a call where nobody answers stores nothing.
    turns: list[Sentence] = Field(min_length=1)


@router.post("/session")
def session() -> dict:
    secret = _default_client().realtime.client_secrets.create(session={
        "type": "realtime",
        "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-mini"),
        "instructions": SYSTEM_PROMPT + _VOICE_RULES,
        "tools": _TOOLS,
        # The candidate's words as text, so the recruiter can read the call.
        "audio": {"input": {"transcription": {"model": "gpt-transcribe"},
                            # Background noise kept cutting Rita off: filter it (laptop mic or
                            # headset) and ask for clearer, longer speech than the defaults (0.5, 500 ms).
                            "noise_reduction": {"type": "near_field"},
                            "turn_detection": {"type": "server_vad", "threshold": 0.65,
                                               "silence_duration_ms": 700}},
                  "output": {"voice": "marin"}},  # a female voice: Rita
    })
    return {"conversation_id": str(uuid4()), "client_secret": secret.value}


@router.post("/tool")
def tool(body: ToolBody) -> dict:
    """Run one tool call for the model. The reply goes back to the model as is:
    validation problems as validation_error, so it re-asks (same as chat).
    A FAQ lookup touches no candidate data, so it skips the row lock."""
    if body.name == "search_faq":
        return dispatch(body.name, {}, body.args)
    with _turn(body.conversation_id, create="voice") as (conn, conv):
        extracted = conv["extracted_fields"]
        out = dispatch(body.name, extracted, body.args)
        ends = body.name == "end_interview" and out.get("ok")
        db.save_voice_data(conn, body.conversation_id, extracted, *screening_status(extracted),
                           completed=conv["completed"] or bool(ends),
                           summary=body.args["summary"] if ends else None,
                           sentiment=body.args["sentiment"] if ends else None)
    return out


@router.post("/transcript")
def transcript(body: TranscriptBody) -> dict:
    """Store finished sentences of the call, in order. Only a candidate sentence may
    create the conversation: Rita's alone, before anyone answered, gets a 404."""
    turns = [(s.role, s.text) for s in body.turns]
    create = "voice" if any(role == "user" for role, _ in turns) else None
    with _turn(body.conversation_id, create=create) as (conn, _conv):
        db.save_voice_turns(conn, body.conversation_id, turns)
    return {"ok": True}
