"""Screening logic checks: typed answers, city matching, status from the data."""
from datetime import date, timedelta

from prompts import GREETING, SYSTEM_PROMPT
from service_areas import cities, match_city
from tools import OPENAI_TOOL_SCHEMAS, dispatch, screening_status


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


def test_only_two_tools():
    assert [t["function"]["name"] for t in OPENAI_TOOL_SCHEMAS] == ["save_answer", "end_interview"]


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
