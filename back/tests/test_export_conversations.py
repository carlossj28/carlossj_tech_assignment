"""Sample-conversation export from an evals report, offline."""
import pytest

from agent.prompts import GREETING
from scripts.export_conversations import CHOSEN, export


def _run(case_id, failures=()):
    return {"id": case_id, "failures": list(failures), "error": None, "extracted": {"full_name": "Marta"},
            "transcript": [{"candidato": f"hola {case_id}", "rita": "¿Tienes carné?",
                            "tools": [{"name": "save_answer"}], "status": "pending"}]}


def test_exports_first_passing_run_of_each_case(tmp_path):
    report = [_run(c, failures=["mal"]) for c in CHOSEN] + [_run(c) for c in CHOSEN]
    written = export(report, tmp_path)
    assert len(written) == len(CHOSEN)
    md = (tmp_path / written[0]).read_text("utf-8")
    assert md.startswith("# ") and GREETING in md
    assert f"**Candidato:** hola {CHOSEN[0]}" in md and "_herramientas: save_answer_" in md
    assert "**Estado final:** pendiente" in md and '"full_name": "Marta"' in md
    assert all(name in (tmp_path / "README.md").read_text("utf-8") for name in written)


def test_fails_clearly_without_a_passing_run(tmp_path):
    with pytest.raises(SystemExit, match=CHOSEN[0]):
        export([_run(CHOSEN[0], failures=["mal"])], tmp_path)
