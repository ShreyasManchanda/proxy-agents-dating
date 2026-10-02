"""Scoring (SPEC §11). Pure functions: no I/O, no LLM.

Data shapes
  verdicts: {(rater, target): [ {"scores": {dim: 1-10}, "second_date": bool}, ... samples ]}
  debrief:  {rater: [target ids best -> worst]}
"""
from __future__ import annotations

import math
from statistics import fmean, pstdev

from app.config import settings

DIMS = ("candor_ease", "mutual_enjoyment", "attentiveness", "positivity", "coordination",
        "perceived_similarity")
MUTUAL_TAG_GAP = 0.15  # |own_ab - own_ba| below this -> "mutual"


# ---------- primitives ----------

def composite(samples: list[dict], weights: dict[str, float] | None = None) -> float:
    """Weighted mean of the six dimensions, averaged over samples. second_date breaks ties
    (tiny additive term, far below one score step)."""
    w = weights or {d: 1.0 for d in DIMS}
    tot = sum(w.values())
    per = [sum(s["scores"][d] * w[d] for d in DIMS) / tot for s in samples]
    sd = fmean(1.0 if s.get("second_date") else 0.0 for s in samples)
    return fmean(per) + 1e-3 * sd


def percentile_in(value: float, population: list[float], member: bool = True) -> float:
    """0-1 percentile, ties share the midpoint. `member`: value is one of the population.
    A value placed on a foreign (frozen) distribution uses the non-member form, still in [0, 1]."""
    n = len(population)
    less = sum(1 for x in population if x < value)
    eq = sum(1 for x in population if x == value)
    if not member:
        return 0.5 if n == 0 else (less + 0.5 * eq) / n
    if n < 2:
        return 0.5
    return (less + 0.5 * (eq - 1)) / (n - 1)


def rank_percentile(rank: int, n: int) -> float:
    return 0.5 if n < 2 else 1 - (rank - 1) / (n - 1)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = fmean(rx), fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return None if den == 0 else num / den


# ---------- stated-signal conflicts (computed in code, never by an LLM) ----------

def detect_conflicts(sig_a: dict, sig_b: dict, topics: tuple[str, ...] | None = None) -> list[dict]:
    """sig_*: {topic: {"value_normalized": ..., "quote": str}} for conflict-capable topics.
    location_relocation value_normalized: {"country": str, "open_to_relocate": bool}."""
    topics = topics if topics is not None else settings.conflict_topics
    out = []

    def add(topic):
        out.append({"topic": topic, "a_quote": sig_a[topic].get("quote"), "b_quote": sig_b[topic].get("quote")})
    for t in topics:
        if t not in sig_a or t not in sig_b:
            continue
        va, vb = sig_a[t].get("value_normalized"), sig_b[t].get("value_normalized")
        if va is None or vb is None:
            continue
        if t == "family_plans" and {va, vb} == {"wants_kids", "no_kids"}:
            add(t)
        elif t == "relationship_intent" and {va, vb} == {"long_term", "casual"}:
            add(t)
        elif t == "location_relocation":
            ca, cb = (va.get("country") or "").lower(), (vb.get("country") or "").lower()
            if ca and cb and ca != cb and not va.get("open_to_relocate") and not vb.get("open_to_relocate"):
                add(t)
    return out


# ---------- core ----------

def _zscores(comp: dict[int, float], min_n: int, frozen: tuple[float, float] | None = None):
    """z over one rater's own dates. Returns None when too few dates (skip adjustment)."""
    if frozen is not None:
        mean, sd = frozen
    else:
        if len(comp) < min_n:
            return None
        vals = list(comp.values())
        mean, sd = fmean(vals), pstdev(vals)
    return {t: (0.0 if sd == 0 else (c - mean) / sd) for t, c in comp.items()}


def compute_stats(verdicts: dict, debrief: dict, cfg=settings, weights=None) -> dict:
    """Everything that gets frozen for a pool: rater mean/SD, partner effects, and each rater's
    sorted adjusted composites (so later arrivals are placed on the frozen distribution)."""
    comp: dict[int, dict[int, float]] = {}
    for (a, b), samples in verdicts.items():
        comp.setdefault(a, {})[b] = composite(samples, weights)
    mean_sd = {a: (fmean(c.values()), pstdev(c.values())) for a, c in comp.items()
               if len(c) >= cfg.min_dates_for_rater_z}
    z = {a: _zscores(comp[a], cfg.min_dates_for_rater_z) for a in comp}
    by_target: dict[int, list[float]] = {}
    for a, zs in z.items():
        if zs:
            for b, v in zs.items():
                by_target.setdefault(b, []).append(v)
    partner = {b: fmean(v) for b, v in by_target.items()}
    adj_sorted = {}
    for a, c in comp.items():
        vals = [(z[a][b] - cfg.partner_effect_shrink * partner.get(b, 0.0)) if z[a] else c[b] for b in c]
        adj_sorted[a] = sorted(vals)
    return {"rater_mean_sd": mean_sd, "partner_effect": partner, "adj_sorted": adj_sorted}


def own_scores(verdicts: dict, debrief: dict, frozen: dict | None = None, cfg=settings,
               weights=None) -> dict[tuple[int, int], dict]:
    """own_ab for every directed pair (steps 1-5). With `frozen`, raters in frozen are measured
    against frozen stats; raters not in frozen (new people) use stats from their own dates plus
    the frozen partner effects. Pool raters' view of a new person has no debrief component."""
    comp: dict[int, dict[int, float]] = {}
    for (a, b), samples in verdicts.items():
        comp.setdefault(a, {})[b] = composite(samples, weights)

    fro_ms = (frozen or {}).get("rater_mean_sd", {})
    fro_pe = (frozen or {}).get("partner_effect", {})
    fro_adj = (frozen or {}).get("adj_sorted", {})
    pool_raters = set(fro_adj)

    z = {}
    for a, c in comp.items():
        z[a] = _zscores(c, cfg.min_dates_for_rater_z, fro_ms.get(a)) if frozen else None
        if z[a] is None:
            z[a] = _zscores(c, cfg.min_dates_for_rater_z)
    if frozen is None:
        partner = compute_stats(verdicts, debrief, cfg, weights)["partner_effect"]
    else:
        partner = dict(fro_pe)
        # new targets: partner effect from pool raters' z of them under frozen stats
        by_t: dict[int, list[float]] = {}
        for a in pool_raters & set(comp):
            for b, v in (z[a] or {}).items():
                if b not in fro_pe:
                    by_t.setdefault(b, []).append(v)
        for b, v in by_t.items():
            partner[b] = fmean(v)

    out = {}
    for a, c in comp.items():
        adj = {b: (z[a][b] - cfg.partner_effect_shrink * partner.get(b, 0.0)) if z[a] else c[b] for b in c}
        # percentile population: frozen distribution for pool raters, own dates otherwise
        on_frozen = bool(frozen) and a in pool_raters
        pop = fro_adj[a] if on_frozen else list(adj.values())
        ranking = debrief.get(a)
        for b, v in adj.items():
            new_target_for_pool_rater = on_frozen and b not in fro_pe
            # existing pool pairs are members of the frozen distribution; a new target is not
            parts = [percentile_in(v, pop, member=not new_target_for_pool_rater)]
            if ranking and b in ranking and not new_target_for_pool_rater:
                parts.append(rank_percentile(ranking.index(b) + 1, len(ranking)))
            out[(a, b)] = {"own": fmean(parts), "adj": v, "composite": c[b],
                           "composite_only": len(parts) == 1}
    return out


def final_scores(own: dict, conflicts: dict[tuple[int, int], list[dict]] | None = None,
                 own_weight: float | None = None, cfg=settings) -> dict[tuple[int, int], dict]:
    """Steps 6-8. Pure: re-callable with a new own_weight for the slider (no LLM)."""
    w = cfg.own_weight if own_weight is None else own_weight
    out = {}
    for (a, b), r in own.items():
        back = own.get((b, a))
        if back is not None:
            mutual = math.sqrt(r["own"] * back["own"])
        else:
            mutual = r["own"]  # missing cell: sparse fallback
        confl = (conflicts or {}).get((a, b)) or (conflicts or {}).get((b, a)) or []
        penalty = cfg.stated_conflict_penalty if confl else 0.0
        final = max(0.0, w * r["own"] + (1 - w) * mutual - penalty)
        if back is None:
            tag = "one-sided data"
        elif abs(r["own"] - back["own"]) <= MUTUAL_TAG_GAP:
            tag = "mutual"
        elif r["own"] > back["own"]:
            tag = "you like them more"
        else:
            tag = "they like you more"
        out[(a, b)] = {**r, "their_own": back["own"] if back else None, "mutual": mutual,
                       "penalty": penalty, "conflicts": confl, "final": final, "tag": tag,
                       "mutual_composite_only": bool(r["composite_only"] or (back and back["composite_only"]))}
    return out


def rankings(final: dict) -> dict[int, list[dict]]:
    by: dict[int, list[dict]] = {}
    for (a, b), r in final.items():
        by.setdefault(a, []).append({"target": b, **r})
    for a in by:
        by[a].sort(key=lambda x: (-x["final"], x["target"]))
        for i, row in enumerate(by[a], 1):
            row["rank"] = i
    return by


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Reliability panel: test-retest and richness-vs-score correlations (reported, never adjusted)."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = fmean(xs), fmean(ys)
    den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return None if den == 0 else sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / den


def order_bias(first_scores: list[float], swapped_scores: list[float]) -> float | None:
    """Mean score shift when the speaker order is swapped (paired by date)."""
    if len(first_scores) != len(swapped_scores) or not first_scores:
        return None
    return fmean(b - a for a, b in zip(first_scores, swapped_scores))


def hypothesis_panel(adj: dict, sim: dict, comp: dict) -> dict:
    """Spearman of each baseline with the adjusted composite over all directed pairs (§11.10).
    Reports whatever the data shows; baselines are never tuned."""
    keys = sorted(set(adj) & set(sim) & set(comp))
    y = [adj[k] for k in keys]
    return {"n_pairs": len(keys),
            "similarity": spearman([sim[k] for k in keys], y),
            "complement": spearman([comp[k] for k in keys], y)}
