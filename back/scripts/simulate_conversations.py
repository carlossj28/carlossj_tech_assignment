"""Simulated candidates talk to the real agent: sample conversations end to end.

Run:  uv run python -m scripts.simulate_conversations OUT_DIR [persona ...]
A second model plays each persona (it reacts to Rita, unlike the scripted evals);
Rita is the real run_turn. Writes one Markdown per persona plus simulaciones.json.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.runner import _default_client, _model_kwargs, run_turn
from scripts.export_conversations import to_markdown

MAX_TURNS = 14
PERSONAS = [
    ("marta", "Marta López, de Madrid. Tienes carné. Jornada completa, prefieres mañanas. 2 años en Glovo. "
              "Puedes empezar el 1 de diciembre. Para la entrevista te va mejor por la mañana."),
    ("javier", "Javier Ruiz, de Valencia. Tienes carné. Media jornada, por las tardes. 3 años en Uber Eats y "
               "Just Eat. Puedes empezar en dos semanas. Para la entrevista, cualquier día por la tarde."),
    ("lucia", "Lucía Fernández, de Sevilla. Tienes carné. Solo fines de semana, horario flexible. Nunca has "
              "repartido. Puedes empezar ya. Para la entrevista te da igual el día."),
    ("andres", "Andrés Gómez, mexicano, vives en CDMX. Tienes licencia de manejo. Tiempo completo, de noche. "
               "1 año en Rappi y DiDi Food. Empiezas el lunes. Para la entrevista, lo antes posible."),
    ("sofia", "Sofía Martínez, mexicana, de Guadalajara. Tienes licencia. Medio tiempo, en las mañanas. Sin "
              "experiencia. Empiezas el 15 de noviembre. Para la entrevista, en la mañana."),
    ("daniel", "Daniel Smith, British, living in Barcelona; you only write in English. You have a driving "
               "licence. Full time, afternoons. 4 years with Deliveroo and Glovo. You can start next month. "
               "For the interview, any afternoon."),
    ("elena", "Elena Ruiz, de Bilbao. No tienes carné de conducir."),
    ("raul", "Raúl Torres, vives en Zaragoza. Tienes carné."),
    ("carmen", "Carmen Díaz, de Málaga. Tienes carné. Media jornada, mañanas. 1 año en Glovo. Puedes empezar "
               "el 1 de diciembre. Antes de decir tu experiencia, preguntas cuánto se cobra. Para la "
               "entrevista, por la mañana."),
    ("diego", "Diego Hernández, de Monterrey. Tienes licencia. Tiempo completo, horario flexible. 5 años en "
              "Uber Eats. Empiezas el 1 de diciembre. En tu primer mensaje das nombre, licencia y ciudad "
              "juntos. Para la entrevista te da igual."),
]
_CANDIDATE = ("Eres un candidato a repartidor que habla por chat con Rita, la asistente de selección. "
              "Tu perfil: {persona}\nResponde como en WhatsApp: corto, natural, solo a lo que te pregunta. "
              "No inventes datos fuera de tu perfil. Si te ofrece huecos de entrevista, elige uno.")


def _candidate_says(persona: str, history: list[dict], client) -> str:
    # The candidate sees the chat from its side: Rita is the "user".
    flipped = [{"role": "user" if m["role"] == "assistant" else "assistant", "content": m["content"]}
               for m in history]
    messages = [{"role": "system", "content": _CANDIDATE.format(persona=persona)}, *flipped]
    completion = client.chat.completions.create(**_model_kwargs(), messages=messages)
    return completion.choices[0].message.content.strip()


def simulate(persona: str, client=None) -> dict:
    client = client or _default_client()
    extracted: dict = {}
    history = [{"role": "assistant", "content": run_turn([], extracted).reply}]  # fixed greeting
    run = {"transcript": [], "extracted": extracted, "summary": None, "completed": False}
    for _ in range(MAX_TURNS):
        said = _candidate_says(persona, history, client)
        history.append({"role": "user", "content": said})
        r = run_turn(history, extracted, client=client)
        history.append({"role": "assistant", "content": r.reply})
        run["transcript"].append({"candidato": said, "rita": r.reply, "tools": r.tool_calls, "status": r.status})
        if r.completed:
            run.update(summary=r.summary, completed=True)
            break
    return run


def main() -> None:
    out, only = Path(sys.argv[1]), sys.argv[2:]
    out.mkdir(parents=True, exist_ok=True)
    personas = [(n, p) for n, p in PERSONAS if not only or n in only]
    with ThreadPoolExecutor(max_workers=5) as pool:
        runs = list(pool.map(simulate, [p for _, p in personas]))
    for (name, persona), run in zip(personas, runs):
        (out / f"{name}.md").write_text(to_markdown(persona, run) + f"\n**Resumen para el reclutador:** "
                                        f"{run['summary']}\n", "utf-8")
        print(f"{name:<8} {run['transcript'][-1]['status']:<13} cerrada={run['completed']} "
              f"turnos={len(run['transcript'])}")
    (out / "simulaciones.json").write_text(
        json.dumps(dict(zip([n for n, _ in personas], runs)), ensure_ascii=False, indent=2, default=str), "utf-8")


if __name__ == "__main__":
    main()
