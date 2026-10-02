import pytest

from app.extract.validators import (VERDICT_DIMS, cap_confidence, quote_in_transcript, turn_problems,
                                    valid_refs, validate_claims, validate_contradictions,
                                    validate_stated, verdict_ok)
from app.scoring.core import order_bias, pearson

OBS = {"o1": {"source": "ig"}, "o2": {"source": "li"}, "o3": {"source": "li"}}


def test_bad_refs_and_kinds_dropped():
    kept, dropped = valid_refs({"abc", "bio"}, [
        {"kind": "hobby", "text": "climbs", "ref": "abc", "weight": 3},
        {"kind": "hobby", "text": "x", "ref": "zzz"},
        {"kind": "religion", "text": "x", "ref": "bio"}])
    assert len(kept) == 1 and kept[0]["weight"] == 1.0 and len(dropped) == 2


def test_stated_quote_must_be_exact_and_topic_allowed():
    text = "Hindu and vegetarian. Want kids someday."
    got = validate_stated([
        {"topic": "diet", "value": "vegetarian", "quote": "vegetarian", "ref": "bio"},
        {"topic": "family_plans", "quote": "Want kids someday", "ref": "bio", "value_normalized": "wants_kids"},
        {"topic": "diet", "quote": "vegan", "ref": "bio"},                      # not in text
        {"topic": "sexual_orientation", "quote": "Hindu", "ref": "bio"},        # D1: never extracted
        {"topic": "family_plans", "quote": "Want kids", "ref": "bio", "value_normalized": "banana"},
    ], text, {"bio"})
    assert [g["topic"] for g in got] == ["diet", "family_plans", "family_plans"]
    assert got[2]["value_normalized"] is None


def test_claims_and_contradictions():
    claims = validate_claims([{"claim": "a", "evidence": ["o1"], "confidence": 0.99},
                              {"claim": "b", "evidence": ["o1", "nope"], "confidence": 0.5},
                              {"claim": "c", "evidence": [], "confidence": 0.5}], OBS, 0.2)
    assert len(claims) == 1 and claims[0]["confidence"] < 0.6
    assert cap_confidence(0.9, 5, 1.0) == 0.9 and cap_confidence(0.9, 1, 0.0) < 0.25
    cs = validate_contradictions([{"evidence": ["o1", "o2"]}, {"evidence": ["o2", "o3"]},
                                  {"evidence": ["o1"]}], OBS)
    assert cs == [{"evidence": ["o1", "o2"]}]


def test_turn_guards():
    persona = "I run a small design studio in Pune and spend weekends bouldering with friends near the river"
    assert turn_problems("word " * 80, persona, None, 70) == ["too_long"]
    assert "banned_phrase" in turn_problems("That's so interesting, tell me more", persona, None, 70)
    assert "quotes_persona" in turn_problems(
        "Well I run a small design studio in Pune and spend weekends", persona, None, 70)
    partner = "I really enjoy cooking dinner for friends on Sunday evenings"
    assert "echo" in turn_problems("I really enjoy cooking dinner for friends on Sunday evenings", persona, partner, 70)
    assert turn_problems("Mostly climbing. What does your week look like?", persona, partner, 70) == []


def test_verdict_checks():
    tr = [{"text": "Honestly I'd rather stay in."}]
    good = {"scores": {d: 6 for d in VERDICT_DIMS}, "second_date": True, "reason": "fine",
            "quote": "rather stay in"}
    assert verdict_ok(good, tr) and quote_in_transcript("stay in", tr)
    assert not verdict_ok({**good, "quote": "made up"}, tr)
    assert not verdict_ok({**good, "scores": {**good["scores"], "positivity": 11}}, tr)
    assert not verdict_ok({"scores": {}}, tr)


def test_diagnostic_helpers():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None
    assert order_bias([5, 6], [6, 7]) == 1.0 and order_bias([], []) is None


def test_snap_quote_forgives_punctuation_only():
    from app.extract.validators import snap_quote
    tr = [{"text": "Honestly I’d rather stay in — it’s been a long week."}]
    assert snap_quote("Honestly I'd rather stay in - it's been a long week", tr) == tr[0]["text"][:-1]
    assert snap_quote("I would rather go out tonight", tr) is None   # words differ: not forgiven
    assert snap_quote("rather  stay in", tr) == "rather stay in"      # spacing-only drift snaps to verbatim
    assert snap_quote("made up words that never appear", tr) is None
    assert snap_quote("short", tr) is None


def test_visual_sensitive_filter():
    from app.extract.validators import visually_safe
    assert not visually_safe("standing together in traditional attire")
    assert not visually_safe("outside a temple")
    assert not visually_safe("Muslim wedding")
    assert visually_safe("hiking with friends at sunrise")
    assert visually_safe("holding a hand-painted ceramic bowl")
    assert visually_safe(None)
