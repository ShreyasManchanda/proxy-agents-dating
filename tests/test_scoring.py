import math

import pytest

from app.scoring.core import (DIMS, compute_stats, composite, detect_conflicts, final_scores,
                              hypothesis_panel, own_scores, percentile_in, rank_percentile, rankings,
                              spearman)


def V(score, second=False):
    return [{"scores": {d: score for d in DIMS}, "second_date": second}]


def grid(n, fn, ids=None):
    ids = ids or list(range(n))
    return {(a, b): V(fn(a, b)) for a in ids for b in ids if a != b}


def noise(a, b):  # deterministic pseudo-noise in [3, 7]
    return 3 + ((a * 7 + b * 13 + a * b) % 9) / 2


def test_primitives():
    assert percentile_in(5, [1, 5, 9]) == 0.5
    assert percentile_in(9, [1, 5, 9]) == 1.0
    assert percentile_in(3, [3, 3, 3]) == 0.5  # ties share midpoint
    assert 0 <= percentile_in(1, [3, 4, 5], member=False) <= 1 and percentile_in(9, [3, 4, 5], member=False) == 1.0
    assert rank_percentile(1, 5) == 1.0 and rank_percentile(5, 5) == 0.0
    assert composite(V(8)) == pytest.approx(8, abs=0.01)
    assert composite(V(8, True)) > composite(V(8, False))  # second_date breaks ties
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2], [1, 2]) is None


def test_charismatic_profile_does_not_dominate():
    n = 10
    v = grid(n, lambda a, b: 9.5 if b == 0 else noise(a, b))
    own = own_scores(v, {})
    ranks = rankings(final_scores(own))
    pos = [next(r["rank"] for r in ranks[a] if r["target"] == 0) for a in range(1, n)]
    assert sum(1 for p in pos if p == 1) <= 2
    assert sum(pos) / len(pos) > 2.5  # not hugging the top


def test_picky_rater_still_gets_a_spread():
    n = 8
    v = grid(n, lambda a, b: (noise(a, b) / 3 if a == 1 else noise(a, b)))
    own = own_scores(v, {})
    vals = [o["own"] for (a, _), o in own.items() if a == 1]
    assert max(vals) == pytest.approx(1.0) or max(vals) > 0.9
    assert min(vals) < 0.15  # normalized, so low scorer's range is not squashed


def test_symmetric_pair_is_mutual():
    v = grid(6, lambda a, b: 8 if {a, b} == {0, 1} else noise(a, a) )
    fin = final_scores(own_scores(v, {}))
    assert fin[(0, 1)]["tag"] == "mutual" and fin[(1, 0)]["tag"] == "mutual"


def test_asymmetric_tags():
    v = grid(6, lambda a, b: noise(a, a))
    v[(0, 1)] = V(9.5)
    v[(1, 0)] = V(2)
    fin = final_scores(own_scores(v, {}))
    assert fin[(0, 1)]["tag"] == "you like them more"
    assert fin[(1, 0)]["tag"] == "they like you more"


def test_missing_cells_dont_crash():
    v = grid(6, noise)
    del v[(1, 0)]
    fin = final_scores(own_scores(v, {}))
    assert fin[(0, 1)]["tag"] == "one-sided data"
    assert 0 <= fin[(0, 1)]["final"] <= 1


def test_sparse_rater_skips_adjustment():
    v = {(0, b): V(noise(0, b)) for b in (1, 2, 3)}  # 3 dates < MIN_DATES_FOR_RATER_Z
    own = own_scores(v, {})
    assert set(own) == {(0, 1), (0, 2), (0, 3)}
    assert all(0 <= o["own"] <= 1 for o in own.values())


def test_debrief_rank_contributes():
    v = grid(6, lambda a, b: 5)  # all equal composites -> 0.5 each
    deb = {0: [1, 2, 3, 4, 5]}
    own = own_scores(v, deb)
    assert own[(0, 1)]["own"] == pytest.approx((0.5 + 1.0) / 2)
    assert own[(0, 5)]["own"] == pytest.approx((0.5 + 0.0) / 2)


def test_conflict_penalty_and_detection():
    a = {"family_plans": {"value_normalized": "wants_kids", "quote": "I want kids"}}
    b = {"family_plans": {"value_normalized": "no_kids", "quote": "child-free"}}
    c = detect_conflicts(a, b)
    assert c and c[0]["topic"] == "family_plans" and c[0]["b_quote"] == "child-free"
    assert detect_conflicts(a, {"family_plans": {"value_normalized": "open", "quote": "x"}}) == []
    loc = lambda ctry, o: {"location_relocation": {"value_normalized": {"country": ctry, "open_to_relocate": o}, "quote": "q"}}
    assert detect_conflicts(loc("IN", False), loc("US", False))
    assert not detect_conflicts(loc("IN", False), loc("US", True))
    # topics outside CONFLICT_TOPICS never trigger
    assert detect_conflicts({"diet": {"value_normalized": "veg"}}, {"diet": {"value_normalized": "meat"}}) == []

    v = grid(6, noise)
    own = own_scores(v, {})
    base = final_scores(own)[(0, 1)]["final"]
    pen = final_scores(own, {(0, 1): c})[(0, 1)]
    assert pen["penalty"] == 0.05 and pen["final"] == pytest.approx(max(0, base - 0.05))
    # conflict is symmetric
    assert final_scores(own, {(1, 0): c})[(0, 1)]["penalty"] == 0.05


def test_slider_is_pure():
    own = own_scores(grid(6, noise), {})
    f1 = final_scores(own, own_weight=1.0)[(0, 1)]
    assert f1["final"] == pytest.approx(f1["own"])
    f0 = final_scores(own, own_weight=0.0)[(0, 1)]
    assert f0["final"] == pytest.approx(f0["mutual"])


def test_new_person_against_frozen_stats():
    pool = list(range(6))
    v = grid(6, noise)
    stats = compute_stats(v, {})
    before = own_scores(v, {}, frozen=stats)

    NEW = 99
    v2 = dict(v)
    for p in pool:
        v2[(NEW, p)] = V(noise(NEW, p))
        v2[(p, NEW)] = V(8)
    after = own_scores(v2, {}, frozen=stats)
    # pool members' views of each other never change
    for k, o in before.items():
        assert after[k]["own"] == pytest.approx(o["own"])
    # pool raters' view of the new person is composite-only; the new person's own view is scored too
    assert all(after[(p, NEW)]["composite_only"] for p in pool)
    assert all((NEW, p) in after for p in pool)
    fin = final_scores(after)
    assert fin[(0, NEW)]["mutual_composite_only"] is True
    assert math.isfinite(fin[(NEW, 0)]["final"])


def test_hypothesis_panel_reports_data():
    adj = {(0, 1): 1.0, (0, 2): 0.0, (0, 3): -1.0, (1, 0): 0.5}
    sim = {(0, 1): 0.9, (0, 2): 0.5, (0, 3): 0.1, (1, 0): 0.7}
    comp = {(0, 1): 0.1, (0, 2): 0.5, (0, 3): 0.9, (1, 0): 0.3}
    h = hypothesis_panel(adj, sim, comp)
    assert h["similarity"] > 0.5 and h["complement"] < -0.5 and h["n_pairs"] == 4
