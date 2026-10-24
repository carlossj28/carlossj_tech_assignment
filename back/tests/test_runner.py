"""Runner checks with a fake OpenAI client (no network).

The fake replays a scripted list of completions: each turn pops the next one.
A completion is either tool calls or a final text reply — same shape the real
SDK returns, so the runner can't tell the difference.
"""
from datetime import date
from types import SimpleNamespace

from agent.prompts import GREETING
from agent.runner import run_turn


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
        _completion(tools=[_tool_call("end_interview", {"summary": "apta", "sentiment": "positive"})]),
        _completion(text="¡Todo listo! El equipo te contactará."),
    ])
    r = run_turn([{"role": "user", "content": "confirmo"}], extracted, client=client)
    assert r.completed and r.status == "qualified" and r.summary == "apta"
    assert r.sentiment == "positive"


def test_one_save_per_turn_rejects_a_second_one():
    # Evals: after saving the name, the model saved a license nobody had given yet.
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"full_name": "Marta"})]),
        _completion(tools=[_tool_call("save_answer", {"has_driver_license": True})]),
        _completion(text="¡Genial, Marta! ¿Tienes carné de conducir?"),
    ])
    extracted = {}
    r = run_turn([{"role": "user", "content": "Me llamo Marta"}], extracted, client=client)
    assert extracted == {"full_name": "Marta"}
    assert "validation_error" in r.tool_calls[1]["result"]


def test_a_failed_save_can_be_retried_in_the_same_turn():
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"city": ""})]),         # validation_error
        _completion(tools=[_tool_call("save_answer", {"city": "Madrid"})]),
        _completion(text="¡Genial! ¿Tienes carné?"),
    ])
    extracted = {}
    run_turn([{"role": "user", "content": "Vivo en Madrid"}], extracted, client=client)
    assert extracted == {"city": "Madrid"}


def test_iteration_cap_falls_back():
    # A model that always asks for a tool never terminates → runner must bail gracefully.
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"full_name": "Ana"})])
        for _ in range(10)
    ])
    r = run_turn([{"role": "user", "content": "hola"}], {}, client=client)
    assert "problema técnico" in r.reply


def test_model_sees_saved_data_and_text_only_history():
    seen = {}

    def create(**kw):
        seen["messages"] = kw["messages"]
        return _completion(text="¿En qué ciudad vives?")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    run_turn([{"role": "assistant", "content": "¿Carné?"}, {"role": "user", "content": "sí"}],
             {"has_driver_license": True}, client=client)
    data_line = seen["messages"][1]
    assert data_line["role"] == "system" and '"has_driver_license": true' in data_line["content"]
    assert date.today().isoformat() in data_line["content"]   # resolves "el lunes que viene"
    assert [m["role"] for m in seen["messages"][2:4]] == ["assistant", "user"]


def test_malformed_tool_args_dont_crash_the_turn():
    bad = SimpleNamespace(id="c_bad", function=SimpleNamespace(name="save_answer", arguments="{not json"))
    client = FakeClient([_completion(tools=[bad]), _completion(text="Perdona, ¿me lo repites?")])
    r = run_turn([{"role": "user", "content": "hola"}], {}, client=client)
    assert r.reply == "Perdona, ¿me lo repites?"
    assert r.tool_calls[0]["result"]["ok"] is False


def test_knockout_without_close_is_closed_keeping_ritas_goodbye():
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"city": "Zaragoza"})]),
        _completion(text="Lo siento, no cubrimos Zaragoza. Si tienes cualquier otra duda, escríbeme."),
        _completion(tools=[_tool_call("end_interview", {"summary": "Fuera de zona.", "sentiment": "neutral"})]),
        _completion(text="Hecho."),
    ])
    r = run_turn([{"role": "user", "content": "Vivo en Zaragoza"}], {"has_driver_license": True}, client=client)
    assert r.completed and r.knockout == "out_of_service_area" and r.sentiment == "neutral"
    assert r.reply.startswith("Lo siento, no cubrimos Zaragoza")       # her goodbye, not "Hecho."


def test_no_extra_close_when_the_knockout_was_already_there():
    client = FakeClient([_completion(text="Si puedes en otra ciudad, dímelo.")])  # one call only
    r = run_turn([{"role": "user", "content": "vale"}], {"city": "Zaragoza"}, client=client)
    assert not r.completed and r.reply == "Si puedes en otra ciudad, dímelo."
