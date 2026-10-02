"""Code validators that gate LLM output (SPEC §8.1, §8.2, §8.3, §10). No LLM here."""
from __future__ import annotations

import re

# Topics that may be extracted. Everything else (gender identity, orientation, health, caste,
# immigration status) is refused even when stated (D1).
ALLOWED_STATED_TOPICS = {"relationship_intent", "family_plans", "faith_practice", "diet",
                         "political_stance", "causes", "languages", "location_relocation"}
OBS_KINDS = {"hobby", "trait", "work", "value", "style", "habit", "taste", "wildcard", "stated_signal"}
CONF_ENUMS = {"family_plans": {"wants_kids", "no_kids", "open"},
              "relationship_intent": {"long_term", "casual", "open"}}
BANNED_TURN_PHRASES = ("i love that", "that's so interesting", "that's amazing", "passionate about", "journey")
VERDICT_DIMS = ("candor_ease", "mutual_enjoyment", "attentiveness", "positivity", "coordination",
                "perceived_similarity")


# D1 backstop for the vision stage: visual descriptions that invite religion, ethnicity, health or
# orientation inference never become observations or reach synthesis, whatever the model wrote.
_SENSITIVE_WORDS = (
    "traditional|ethnic|cultural|religious|attire|garb|costume|hijab|burqa|niqab|turban|bindi|sindoor|"
    "kippah|yarmulke|cross|crucifix|rosary|tilak|temple|church|mosque|gurdwara|synagogue|prayer|puja|"
    "wheelchair|cane|prosthetic|hospital|pride|rainbow flag|lgbt" + r"\w*" + "|skin|complexion|race|racial|"
    "muslim|hindu|christian|sikh|jewish|buddhist")
SENSITIVE_VISUAL = re.compile(r"\b(?:" + _SENSITIVE_WORDS + r")\b", re.I)


def visually_safe(text: str | None) -> bool:
    return not (text and SENSITIVE_VISUAL.search(text))


def valid_refs(raw_refs: set[str], observations: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop observations whose ref isn't in the raw data. Returns (kept, dropped)."""
    kept, dropped = [], []
    for o in observations:
        ok = (isinstance(o, dict) and o.get("kind") in OBS_KINDS and str(o.get("ref")) in raw_refs
              and isinstance(o.get("text"), str) and o["text"].strip())
        (kept if ok else dropped).append(o)
    for o in kept:
        o["weight"] = min(1.0, max(0.0, float(o.get("weight", 0.5))))
        o["confidence"] = min(1.0, max(0.0, float(o.get("confidence", 0.5))))
    return kept, dropped


def validate_stated(items: list[dict], own_text: str, refs: set[str]) -> list[dict]:
    """Keep only quotes that are exact substrings of the person's own text, on allowed topics."""
    out = []
    for it in items:
        if it.get("topic") not in ALLOWED_STATED_TOPICS:
            continue
        q = it.get("quote") or ""
        if not q or q not in own_text or str(it.get("ref")) not in refs:
            continue
        enum = CONF_ENUMS.get(it["topic"])
        if enum is not None and it.get("value_normalized") not in enum:
            it = {**it, "value_normalized": None}  # unknown enum value: keep the quote, no code conflict
        out.append(it)
    return out


def cap_confidence(conf: float, n_evidence: int, richness_score: float) -> float:
    """Evidence count and richness cap the model's own confidence."""
    cap = min(1.0, 0.35 + 0.15 * n_evidence) * (0.4 + 0.6 * max(0.0, min(1.0, richness_score)))
    return round(min(conf, cap), 3)


def validate_claims(claims: list[dict], obs_by_id: dict[str, dict], richness_score: float) -> list[dict]:
    """Drop claims citing missing ids; cap confidence."""
    out = []
    for c in claims:
        cited = c.get("evidence") or []
        ev = [e for e in cited if e in obs_by_id]
        if not ev or len(ev) != len(cited):
            continue
        out.append({**c, "evidence": ev,
                    "confidence": cap_confidence(float(c.get("confidence", 0.5)), len(ev), richness_score)})
    return out


def validate_contradictions(items: list[dict], obs_by_id: dict[str, dict]) -> list[dict]:
    """A contradiction needs two cited observations, one from each source (ig and li)."""
    out = []
    for c in items:
        ev = c.get("evidence") or []
        if len(ev) >= 2 and all(e in obs_by_id for e in ev) and {obs_by_id[e]["source"] for e in ev} == {"ig", "li"}:
            out.append(c)
    return out


# ---------- date guards (§10) ----------

def _words(s: str) -> list[str]:
    return re.findall(r"[\w']+", s.lower())


def turn_problems(text: str, persona_text: str, partner_last: str | None, max_words: int) -> list[str]:
    probs = []
    if len(text.split()) > max_words:
        probs.append("too_long")
    if any(p in text.lower() for p in BANNED_TURN_PHRASES):
        probs.append("banned_phrase")
    w = _words(text)
    # verbatim quoting of the persona card: an 8-word run from the card appears in the turn
    pw = _words(persona_text)
    grams = {" ".join(pw[i:i + 8]) for i in range(max(0, len(pw) - 7))}
    if any(" ".join(w[i:i + 8]) in grams for i in range(max(0, len(w) - 7))):
        probs.append("quotes_persona")
    if partner_last:
        pl = set(_words(partner_last))
        if w and len(pl) >= 4 and len(set(w) & pl) / len(set(w)) > 0.85:
            probs.append("echo")
    return probs


def quote_in_transcript(quote: str, transcript: list[dict]) -> bool:
    return bool(quote) and any(quote in t.get("text", "") for t in transcript)


_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "‑": "-", "‐": "-",
                        "–": "-", "—": "-", " ": " ", "…": "..."})


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercased, punctuation-folded, whitespace-collapsed text plus a map to original indices."""
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(text.translate(_PUNCT)):
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch.lower())
        idx.append(i)
    return "".join(out), idx


def snap_quote(quote: str, transcript: list[dict]) -> str | None:
    """If the model's quote matches a transcript line except for punctuation or spacing, return the
    exact transcript text (so the stored quote is always a verbatim substring); otherwise None."""
    q, _ = _norm_with_map(quote or "")
    q = q.strip().rstrip(".")
    if len(q) < 8:
        return None
    for t in transcript:
        text = t.get("text", "")
        norm, idx = _norm_with_map(text)
        at = norm.find(q)
        if at >= 0:
            return text[idx[at]: idx[at + len(q) - 1] + 1]
    return None


def verdict_ok(v: dict, transcript: list[dict]) -> bool:
    try:
        return (all(1 <= float(v["scores"][d]) <= 10 for d in VERDICT_DIMS)
                and isinstance(v["second_date"], bool)
                and len(str(v["reason"]).split()) <= 40
                and quote_in_transcript(v["quote"], transcript))
    except (KeyError, TypeError, ValueError):
        return False
