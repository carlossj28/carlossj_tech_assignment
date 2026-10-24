"""Eval harness checks, offline (fake client, no tokens).

The evals themselves hit the real model (python -m evals); here we only make
sure the checker judges correctly and the cases file is well-formed.
"""
from types import SimpleNamespace

from test_runner import FakeClient, _completion, _tool_call

from agent.schemas import SaveAnswerArgs
from agent.tools import INTERVIEW_KEY
from evals.harness import check, load_cases, run_case

_EXPECT_KEYS = {"saved", "not_saved", "present", "status", "knockout", "completed", "reply_lang", "booked",
                "slot_part", "sentiment", "tools_called"}


def _r(status="pending", knockout=None, completed=False, reply="Vale", sentiment=None, tools=()):
    return SimpleNamespace(status=status, knockout=knockout, completed=completed, reply=reply,
                           sentiment=sentiment, tool_calls=[{"name": t} for t in tools])


def test_cases_file_is_well_formed():
    cases = load_cases()
    fields = set(SaveAnswerArgs.model_fields)
    assert len({c["id"] for c in cases}) == len(cases)            # unique ids
    for c in cases:
        assert c["title"] and c["turns"]
        for t in c["turns"]:
            exp = t.get("expect", {})
            assert set(exp) <= _EXPECT_KEYS, (c["id"], exp)       # no typo'd keys
            named = {*exp.get("saved", {}), *exp.get("not_saved", []), *exp.get("present", [])}
            assert named <= fields, (c["id"], named - fields)    # real field names only


def test_check_is_loose_on_case_and_list_order():
    extracted = {"full_name": "marta  lópez", "availability": ["weekends", "part_time"],
                 "prior_experience": {"years": 2, "platforms": ["glovo"]}}
    expect = {"saved": {"full_name": "Marta López", "availability": ["part_time", "weekends"],
                        "prior_experience": {"years": 2, "platforms": ["Glovo"]}}}
    assert check(expect, extracted, _r()) == []


def test_check_reports_each_mismatch():
    fails = check({"saved": {"city": "Madrid"}, "not_saved": ["has_driver_license"],
                   "present": ["start_date"], "status": "qualified", "reply_lang": "en"},
                  {"city": "Sevilla", "has_driver_license": True}, _r(reply="¿Tienes carné?"))
    assert len(fails) == 5


def test_check_booking_and_its_part_of_day():
    booked = {INTERVIEW_KEY: "2030-01-07T16:30"}
    assert check({"booked": True, "slot_part": "afternoon"}, booked, _r()) == []
    assert len(check({"slot_part": "morning"}, booked, _r())) == 1          # wrong part of the day
    assert len(check({"booked": True}, {}, _r())) == 1                      # nothing booked
    assert len(check({"booked": False}, booked, _r())) == 1                 # booked when it shouldn't
    assert len(check({"slot_part": "afternoon"}, {}, _r())) == 1            # part asked, no booking


def test_check_sentiment_and_tools_called():
    r = _r(completed=True, sentiment="frustrated", tools=["search_faq", "end_interview"])
    assert check({"sentiment": "frustrated", "tools_called": ["search_faq"]}, {}, r) == []
    assert len(check({"sentiment": "neutral"}, {}, r)) == 1
    assert len(check({"tools_called": ["save_answer"]}, {}, r)) == 1


def test_run_case_plays_the_script_through_the_real_runner():
    case = {"id": "x", "title": "x", "turns": [
        {"say": "No tengo carné", "expect": {"saved": {"has_driver_license": False},
                                              "status": "disqualified", "knockout": "no_license"}}]}
    client = FakeClient([
        _completion(tools=[_tool_call("save_answer", {"has_driver_license": False})]),
        _completion(tools=[_tool_call("end_interview", {"summary": "Sin carné.", "sentiment": "neutral"})]),
        _completion(text="Lo siento, el carné es obligatorio."),
    ])
    res = run_case(case, client=client)
    assert res.passed, res.failures
    assert res.transcript[0]["status"] == "disqualified"


def test_run_case_turns_an_api_error_into_a_failed_case():
    case = {"id": "x", "title": "x", "turns": [{"say": "Hola"}]}
    res = run_case(case, client=FakeClient([]))                    # pop from empty → error
    assert not res.passed and res.error
