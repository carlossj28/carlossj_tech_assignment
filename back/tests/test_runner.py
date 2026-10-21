"""Runner checks with a fake OpenAI client (no network).

The fake replays a scripted list of completions: each turn pops the next one.
A completion is either tool calls or a final text reply — same shape the real
SDK returns, so the runner can't tell the difference.
"""
from types import SimpleNamespace

from prompts import GREETING
from runner import run_turn


def _tool_call(name, args):
    import json
    return SimpleNamespace(id=f"c_{name}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _completion(*, text=None, tools=None):
    msg = SimpleNamespace(content=text, tool_calls=tools)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeClient:
    """Replays scripted completions in order."""
    def __init__(self, script):
        self._script = list(script)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_):
        return self._script.pop(0)


def test_greets_without_calling_the_model():
    r = run_turn([], {})                       # no client: calling the model would fail
    assert r.reply == GREETING and not r.completed


def test_saves_answer_then_replies():
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"full_name": "Marta"})]),
        _completion(text="¡Genial, Marta! ¿Tienes carné de conducir?"),
    ])
    extracted = {}
    r = run_turn([{"role": "user", "content": "soy Marta"}], extracted, client=client)
    assert extracted["full_name"] == "Marta"
    assert "carné" in r.reply
    assert r.status == "pending" and not r.completed


def test_end_interview_completes_with_status_from_data():
    extracted = {"has_driver_license": True, "city": "Madrid"}
    client = FakeClient([
        _completion(tools=[_tool_call("end_interview", {"summary": "apta"})]),
        _completion(text="¡Todo listo! El equipo te contactará."),
    ])
    r = run_turn([{"role": "user", "content": "confirmo"}], extracted, client=client)
    assert r.completed and r.status == "qualified" and r.summary == "apta"


def test_iteration_cap_falls_back():
    # A model that always asks for a tool never terminates → runner must bail gracefully.
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"full_name": "Ana"})])
        for _ in range(10)
    ])
    r = run_turn([{"role": "user", "content": "hola"}], {}, client=client)
    assert "problema técnico" in r.reply
