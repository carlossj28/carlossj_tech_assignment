"""Turn an evals report into readable sample conversations (Markdown).

Run:  uv run python -m scripts.export_conversations informe-evals.json ../docs/conversaciones
Takes the first passing run of each chosen case: real agent runs, scripted candidate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.prompts import GREETING
from evals.harness import load_cases

CHOSEN = ["agenda_entrevista", "todo_en_un_mensaje", "sin_carne", "cambio_idioma", "faq_sueldo", "inyeccion"]
STATUS = {"qualified": "cualificado", "disqualified": "descartado", "pending": "pendiente"}


def to_markdown(title: str, run: dict) -> str:
    lines = [f"# {title}", "", f"**Rita:** {GREETING}", ""]
    for turn in run["transcript"]:
        lines += [f"**Candidato:** {turn['candidato']}", ""]
        tools = ", ".join(t["name"] for t in turn["tools"])
        lines += [f"**Rita:** {turn['rita']}", ""] + ([f"> _herramientas: {tools}_", ""] if tools else [])
    last = run["transcript"][-1]["status"] if run["transcript"] else "pending"
    lines += ["---", "", f"**Estado final:** {STATUS[last]}", "", "**Datos guardados:**", "",
              "```json", json.dumps(run["extracted"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def export(report: list[dict], out_dir: Path) -> list[str]:
    titles = {c["id"]: c["title"] for c in load_cases()}
    out_dir.mkdir(parents=True, exist_ok=True)
    index = ["# Conversaciones de ejemplo", "",
             "Ejecuciones reales del agente (gpt-5.4-mini) con un candidato de guion, sacadas de las evals.", ""]
    written = []
    for n, case_id in enumerate(CHOSEN, 1):
        run = next((r for r in report if r["id"] == case_id and not r["failures"] and not r["error"]), None)
        if run is None:
            raise SystemExit(f"{case_id}: ninguna ejecución correcta en el informe")
        name = f"{n:02d}-{case_id}.md"
        (out_dir / name).write_text(to_markdown(titles[case_id], run), "utf-8")
        index.append(f"{n}. [{titles[case_id]}]({name})")
        written.append(name)
    (out_dir / "README.md").write_text("\n".join(index) + "\n", "utf-8")
    return written


if __name__ == "__main__":
    report_path, out = sys.argv[1:3]
    print(export(json.loads(Path(report_path).read_text("utf-8")), Path(out)))
