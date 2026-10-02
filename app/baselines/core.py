"""Code-only baselines (SPEC §9). Neither is ever tuned to make a hypothesis win.

Profile fields used (all optional):
  tags:   {"values": [...], "lifestyle": [...], "interests": [...]}   canonical vocabulary tags
  stated: {topic: {"value_normalized": ... or None, "value": str}}
  dials:  {"pace": 0-1, "social_style": 0-1, "tempo": 0-1}
There is deliberately no personality-trait similarity.
"""
from app.config import settings

TAG_GROUPS = ("values", "lifestyle", "interests")
DIALS = ("pace", "social_style", "tempo")
VALUES_GATE = 0.2  # complement counts in full only when shared-values Jaccard reaches this


def jaccard(a, b) -> float | None:
    a, b = set(a or ()), set(b or ())
    if not a and not b:
        return None  # nothing to compare: skip the group rather than score it 0
    return len(a & b) / len(a | b)


def _stated_key(entry):
    v = entry.get("value_normalized")
    if v is None:
        v = (entry.get("value") or "").strip().lower() or None
    return repr(sorted(v.items())) if isinstance(v, dict) else v


def stated_agreement(sa: dict, sb: dict) -> float | None:
    shared = [t for t in sa if t in sb and _stated_key(sa[t]) and _stated_key(sb[t])]
    if not shared:
        return None
    return sum(_stated_key(sa[t]) == _stated_key(sb[t]) for t in shared) / len(shared)


def baseline_similarity(a: dict, b: dict) -> float | None:
    """Mean tag overlap over values, lifestyle and interests, blended with stated-signal agreement
    at STATED_SIGNAL_BASELINE_WEIGHT when both people state comparable topics. None = no data."""
    overlaps = [j for g in TAG_GROUPS if (j := jaccard((a.get("tags") or {}).get(g), (b.get("tags") or {}).get(g))) is not None]
    tag = sum(overlaps) / len(overlaps) if overlaps else None
    st = stated_agreement(a.get("stated") or {}, b.get("stated") or {})
    w = settings.stated_signal_baseline_weight
    if tag is None and st is None:
        return None
    if st is None:
        return tag
    if tag is None:
        return st
    return (1 - w) * tag + w * st


def baseline_complement(a: dict, b: dict) -> float | None:
    """Mean absolute difference on pace, social style and tempo, gated on shared values."""
    da, db = a.get("dials") or {}, b.get("dials") or {}
    diffs = [abs(da[d] - db[d]) for d in DIALS if d in da and d in db]
    if not diffs:
        return None
    raw = sum(diffs) / len(diffs)
    sv = jaccard((a.get("tags") or {}).get("values"), (b.get("tags") or {}).get("values"))
    gate = 0.0 if sv is None else min(1.0, sv / VALUES_GATE)
    return raw * gate
