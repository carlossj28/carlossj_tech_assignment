"""P4a runner checks with a fake OpenAI client (no network).

The fake replays a scripted list of completions: each turn pops the next one.
A completion is either tool calls or a final text reply — same shape the real
SDK returns, so the runner can't tell the difference.
"""
from types import SimpleNamespace

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


def test_records_field_then_replies():
    client = FakeClient([
        _completion(tools=[_tool_call("record_field", {"field": "full_name", "value": "Marta", "confidence": 0.9})]),
        _completion(text="¡Genial, Marta! ¿Tienes carné de conducir?"),
    ])
    extracted = {}
    r = run_turn([{"role": "user", "content": "soy Marta"}], extracted, client=client)
    assert extracted["full_name"] == "Marta"
    assert "carné" in r.reply
    assert not r.completed


def test_complete_seals_verdict_via_python():
    extracted = {"has_driver_license": True, "city": "Madrid / Centro"}
    client = FakeClient([
        _completion(tools=[_tool_call("complete_screening", {"summary": "apta"})]),
        _completion(text="¡Todo listo! El equipo te contactará."),
    ])
    r = run_turn([{"role": "user", "content": "confirmo"}], extracted, client=client)
    assert r.completed and r.qualified is True


def test_narrated_close_is_caught():
    extracted = {"has_driver_license": False}
    client = FakeClient([
        _completion(text="Gracias. complete_screening(summary='sin carné')"),
    ])
    r = run_turn([{"role": "user", "content": "no tengo carné"}], extracted, client=client)
    assert r.completed and r.qualified is False       # sealed despite narration
    assert "complete_screening" not in r.reply        # stripped from the visible reply


def test_iteration_cap_falls_back():
    # A model that always asks for a tool never terminates → runner must bail gracefully.
    client = FakeClient([
        _completion(tools=[_tool_call("flag_invalid", {"field": "x", "user_value": "y", "reason": "z"})])
        for _ in range(10)
    ])
    r = run_turn([{"role": "user", "content": "hola"}], {}, client=client)
    assert "problema técnico" in r.reply
