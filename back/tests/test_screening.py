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


def test_license_yes_no_negatives_win():
    e: dict = {}
    dispatch("record_field", e, {"field": "has_driver_license", "value": "no tengo", "confidence": 0.9})
    assert e["has_driver_license"] is False
    dispatch("record_field", e, {"field": "has_driver_license", "value": "claro que sí", "confidence": 0.9})
    assert e["has_driver_license"] is True


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
