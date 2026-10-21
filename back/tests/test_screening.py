"""Screening logic checks: validation, normalization, the safety net."""
from datetime import date, timedelta

from service_areas import match_zone
from tools import dispatch, recompute_qualified


def test_city_match_accents_and_zone_alone():
    assert match_zone("Cuauhtemoc") == "Ciudad de México / Cuauhtémoc"
    assert match_zone("Arganzuela") == "Madrid / Arganzuela"
    assert match_zone("Narnia") is None


def test_city_match_quality_typo_and_partial():
    assert match_zone("Madird Centro") == "Madrid / Centro"          # transposed typo
    assert match_zone("vivo en el centro de Madrid") == "Madrid / Centro"  # partial / noisy


def test_record_city_canonicalizes():
    e: dict = {}
    assert dispatch("record_field", e, {"field": "city", "value": "arganzuela", "confidence": 0.9})["ok"]
    assert e["city"] == "Madrid / Arganzuela"


def test_record_city_rejects_unknown():
    r = dispatch("record_field", {}, {"field": "city", "value": "Narnia", "confidence": 0.9})
    assert r == {"ok": False, "validation_error": "City not in a service area."}


def test_license_accepts_only_yes_or_no():
    # The model interprets the candidate's words; Python only checks the type.
    e: dict = {}
    dispatch("record_field", e, {"field": "has_driver_license", "value": "yes", "confidence": 0.9})
    assert e["has_driver_license"] is True
    dispatch("record_field", e, {"field": "has_driver_license", "value": " No ", "confidence": 0.9})
    assert e["has_driver_license"] is False


def test_license_raw_text_is_rejected_not_guessed():
    # Free text (even "Sí, desde noviembre") is never parsed: the model must send yes/no.
    for raw in ["Sí, desde noviembre", "no tengo", "true"]:
        e: dict = {}
        r = dispatch("record_field", e, {"field": "has_driver_license", "value": raw, "confidence": 0.9})
        assert r["ok"] is False and "has_driver_license" not in e, raw


def test_start_date_future_only():
    past = (date.today() - timedelta(days=1)).isoformat()
    future = (date.today() + timedelta(days=7)).isoformat()
    assert not dispatch("record_field", {}, {"field": "start_date", "value": past, "confidence": 1})["ok"]
    assert dispatch("record_field", {}, {"field": "start_date", "value": future, "confidence": 1})["ok"]


def test_safety_net_seals_verdict():
    assert recompute_qualified({"has_driver_license": True, "city": "Madrid / Centro"}) is True
    assert recompute_qualified({"has_driver_license": False, "city": "Madrid / Centro"}) is False
    assert recompute_qualified({"has_driver_license": True, "city": None}) is False
    assert recompute_qualified({"_disqualified": True, "has_driver_license": True, "city": "Madrid / Centro"}) is False


def test_complete_returns_qualified():
    e = {"has_driver_license": True, "city": "Madrid / Centro"}
    assert dispatch("complete_screening", e, {"summary": "ok"}) == {"ok": True, "qualified": True}


def test_unknown_tool_and_bad_args_dont_raise():
    assert dispatch("nope", {}, {})["ok"] is False
    assert dispatch("record_field", {}, {"field": "city"})["ok"] is False
