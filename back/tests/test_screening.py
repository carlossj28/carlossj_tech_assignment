"""Screening logic checks: typed answers, city matching, status from the data."""
from datetime import date, datetime, timedelta

from prompts import GREETING, SYSTEM_PROMPT
from service_areas import cities, match_city
from tools import INTERVIEW_KEY, OPENAI_TOOL_SCHEMAS, dispatch, open_slots, screening_status


def _save(extracted: dict, **fields) -> dict:
    return dispatch("save_answer", extracted, fields)


def test_city_match_accents_aliases_and_typos():
    assert match_city("cordoba") is None                       # not covered
    assert match_city("Ciudad de mexico") == "Ciudad de México"
    assert match_city("CDMX") == "Ciudad de México"            # alias
    assert match_city("Madird") == "Madrid"                    # transposed typo
    assert match_city("vivo en Valencia") == "Valencia"        # noisy input
    assert match_city("Lerín") is None
    assert match_city("Narnia") is None


def test_save_answer_stores_typed_values():
    e: dict = {}
    r = _save(e, has_driver_license=True, preferred_schedule=["morning"],
              prior_experience={"years": 2, "platforms": ["Glovo"]})
    assert r["ok"]
    assert e["has_driver_license"] is True
    assert e["preferred_schedule"] == ["morning"]
    assert e["prior_experience"] == {"years": 2, "platforms": ["Glovo"]}


def test_save_answer_several_fields_in_one_call():
    e: dict = {}
    assert _save(e, full_name="Marta Gil", has_driver_license=True, city="madrid")["ok"]
    assert e == {"full_name": "Marta Gil", "has_driver_license": True, "city": "Madrid"}


def test_save_answer_rejects_invalid_types_and_saves_nothing():
    past = (date.today() - timedelta(days=1)).isoformat()
    for bad in [{"has_driver_license": "sí, desde noviembre"},
                {"preferred_schedule": ["madrugada"]},
                {"prior_experience": {"years": -1, "platforms": []}},
                {"start_date": past}]:
        e: dict = {}
        r = _save(e, full_name="Ana", **bad)
        assert r["ok"] is False and "validation_error" in r, bad
        assert e == {}, bad                                      # all or nothing


def test_start_date_today_or_later():
    e: dict = {}
    future = (date.today() + timedelta(days=7)).isoformat()
    assert _save(e, start_date=future)["ok"]
    assert e["start_date"] == future


def test_knockout_no_license():
    r = _save({}, has_driver_license=False)
    assert r["status"] == "disqualified" and r["knockout"] == "no_license"


def test_knockout_city_outside_coverage_offers_covered_cities():
    e: dict = {}
    r = _save(e, city="Lerín")
    assert r["status"] == "disqualified" and r["knockout"] == "out_of_service_area"
    assert r["covered_cities"] == cities()
    assert e["city"] == "Lerín"                                  # raw text kept for the recruiter


def test_qualified_needs_license_and_covered_city():
    e: dict = {}
    assert _save(e, has_driver_license=True)["status"] == "pending"
    assert _save(e, city="madird")["status"] == "qualified"


def test_correction_recomputes_status():
    e: dict = {}
    _save(e, has_driver_license=True, city="Lerín")
    assert screening_status(e) == ("disqualified", "out_of_service_area")
    assert _save(e, city="Madrid")["status"] == "qualified"


def test_prompt_lists_every_covered_city():
    for city in cities():
        assert city in SYSTEM_PROMPT


def test_prompt_adapts_to_mexican_spanish():
    assert "español de México" in SYSTEM_PROMPT
    assert "licencia de manejo" in SYSTEM_PROMPT


def test_the_agent_tools():
    assert [t["function"]["name"] for t in OPENAI_TOOL_SCHEMAS] == [
        "save_answer", "end_interview", "find_slots", "book_interview"]


def test_greeting_discloses_assistant():
    assert "asistente" in GREETING


def test_unknown_tool_and_bad_args_dont_raise():
    assert dispatch("nope", {}, {})["ok"] is False
    assert dispatch("save_answer", {}, {"not_a_field": 1})["ok"] is False
    assert dispatch("end_interview", {}, {})["ok"] is False


def test_end_interview_needs_a_known_sentiment():
    ok = {"summary": "Apta, Madrid."}
    assert dispatch("end_interview", {}, ok)["ok"] is False                           # missing
    assert dispatch("end_interview", {}, {**ok, "sentiment": "angry"})["ok"] is False  # unknown
    assert dispatch("end_interview", {}, {**ok, "sentiment": "frustrated"})["ok"] is True


# ── Interview booking (ADR-032) ───────────────────────────────────────────────

QUALIFIED = {"has_driver_license": True, "city": "Madrid"}


def test_open_slots_follow_the_weekly_pattern_from_now():
    monday_9am = datetime(2030, 1, 7, 9, 0)                                 # a Monday
    slots = open_slots(monday_9am)
    assert slots[0] == datetime(2030, 1, 7, 10, 0)                         # first slot of the day
    assert all(s > monday_9am and s.weekday() < 5 for s in slots)          # future, weekdays only
    assert open_slots(datetime(2030, 1, 7, 12, 30))[0].hour == 16          # past morning slots dropped


def test_find_slots_applies_the_candidate_criteria():
    day = open_slots()[0].date()
    afternoon = dispatch("find_slots", dict(QUALIFIED), {"day": day.isoformat(), "part": "afternoon"})
    assert afternoon["ok"] and 1 <= len(afternoon["slots"]) <= 3
    assert all(s.startswith(day.isoformat()) and int(s[11:13]) >= 14 for s in afternoon["slots"])

    later = dispatch("find_slots", dict(QUALIFIED), {"from_date": (day + timedelta(days=7)).isoformat()})
    assert all(s >= (day + timedelta(days=7)).isoformat() for s in later["slots"])
    assert dispatch("find_slots", dict(QUALIFIED), {"part": "evening"})["slots"] == []   # no evening slots


def test_only_a_qualified_candidate_can_book():
    pending = {"has_driver_license": True}
    assert dispatch("find_slots", pending, {})["ok"] is False
    assert dispatch("book_interview", pending, {"slot": open_slots()[0].isoformat()})["ok"] is False


def test_book_interview_takes_only_an_open_slot():
    extracted = dict(QUALIFIED)
    slot = dispatch("find_slots", extracted, {})["slots"][0]
    assert dispatch("book_interview", extracted, {"slot": "2030-01-07T03:00"})["ok"] is False  # not a slot
    booked = dispatch("book_interview", extracted, {"slot": slot})
    assert booked == {"ok": True, "interview_at": slot}
    assert extracted[INTERVIEW_KEY] == slot
