import pytest

from app.baselines.core import baseline_complement, baseline_similarity, jaccard


def P(values=(), life=(), ints=(), stated=None, dials=None):
    return {"tags": {"values": list(values), "lifestyle": list(life), "interests": list(ints)},
            "stated": stated or {}, "dials": dials or {}}


def test_jaccard_empty_is_skipped_not_zero():
    assert jaccard([], []) is None
    assert jaccard(["a"], []) == 0.0


def test_similarity_tags_only_and_none():
    a, b = P(values=["x", "y"], ints=["m"]), P(values=["x"], ints=["m"])
    assert baseline_similarity(a, b) == pytest.approx((0.5 + 1.0) / 2)
    assert baseline_similarity(P(), P()) is None


def test_stated_signals_blend_in_at_configured_weight():
    s = {"family_plans": {"value_normalized": "wants_kids"}, "diet": {"value": "Vegetarian"}}
    t = {"family_plans": {"value_normalized": "wants_kids"}, "diet": {"value": "vegan"}}
    a, b = P(values=["x"], stated=s), P(values=["x"], stated=t)
    # tag overlap 1.0, stated agreement 0.5, weight 0.3 -> 0.7*1 + 0.3*0.5
    assert baseline_similarity(a, b) == pytest.approx(0.85)


def test_complement_gated_on_shared_values():
    dials_a = {"pace": 0.0, "social_style": 0.0, "tempo": 0.0}
    dials_b = {"pace": 1.0, "social_style": 1.0, "tempo": 1.0}
    shared = baseline_complement(P(values=["x"], dials=dials_a), P(values=["x"], dials=dials_b))
    none = baseline_complement(P(values=["x"], dials=dials_a), P(values=["z"], dials=dials_b))
    assert shared == pytest.approx(1.0) and none == 0.0  # opposites with no shared values don't score
    assert baseline_complement(P(values=["x"]), P(values=["x"])) is None
