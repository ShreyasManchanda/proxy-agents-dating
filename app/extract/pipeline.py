"""Extraction (SPEC §8): observers -> validated observations -> synthesis -> persona card.

Every call goes through the Gateway (cached, budgeted). Code validates every ref, quote, claim
and tag so a small model cannot put unsupported content on a public profile page.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from app.config import settings
from app.extract.validators import (valid_refs, validate_claims, validate_contradictions,
                                    validate_stated, visually_safe)
from app.extract.vocab import ALL as VOCAB, clean_tags
from app.llm.gateway import Gateway
from app.llm.util import parse_json

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
_HEADER = (PROMPT_DIR / "header.md").read_text(encoding="utf-8")


def load_prompt(name: str) -> tuple[str, str]:
    """Returns (system text, version). The version hashes the file so edits invalidate the cache."""
    body = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    text = _HEADER + "\n" + body
    return text, f"{name}-" + hashlib.sha1(text.encode()).hexdigest()[:8]


# ---------- building the data blocks (refs are what validators check against) ----------

def ig_block(ig: dict) -> tuple[str, set[str], dict[str, str]]:
    """-> (prompt text, valid refs, own authored text by ref)."""
    refs, own, lines = {"bio"}, {}, []
    if ig.get("bio"):
        own["bio"] = ig["bio"]
    lines.append(f"[bio] {ig.get('bio') or '(empty)'}")
    lines.append(f"followers={ig.get('followers')} following={ig.get('following')} posts={ig.get('posts_count')}")
    for p in ig["posts"]:
        ref = f"p:{p['ref']}"
        refs.add(ref)
        if p["caption"]:
            own[ref] = p["caption"]
        song = f" song='{p['song']}' by '{p['artist']}'" if p.get("song") else ""
        lines.append(f"[{ref}] {p['timestamp']} {'reel' if p['is_reel'] else p['type']}"
                     f"{' (pinned)' if p['pinned'] else ''} caption='{p['caption']}'"
                     f" likes={p['likes']} tagged_people={p['tagged_count']}{song}")
    return "\n".join(lines), refs, own


def li_block(li: dict) -> tuple[str, set[str], dict[str, str]]:
    refs, own, lines = set(), {}, []
    for ref, label, val in (("headline", "headline", li.get("headline")), ("about", "about", li.get("about"))):
        refs.add(ref)
        lines.append(f"[{ref}] {val or '(empty)'}")
        if val:
            own[ref] = val
    loc = li.get("location") or {}
    lines.append(f"location: {', '.join(v for v in loc.values() if v) or 'unknown'}")
    for i, e in enumerate(li.get("experience") or []):
        refs.add(f"exp:{i}")
        lines.append(f"[exp:{i}] {e['position']} at {e['company']} ({e['start']} to {e['end']}) {e.get('description') or ''}")
    for i, e in enumerate(li.get("education") or []):
        refs.add(f"edu:{i}")
        lines.append(f"[edu:{i}] {e['degree']} {e['field']} at {e['school']}")
    if li.get("skills"):
        refs.add("skills")
        lines.append(f"[skills] {', '.join(li['skills'][:20])}")
    for p in li.get("own_posts") or []:
        ref = f"post:{p['ref']}"
        refs.add(ref)
        own[ref] = p["text"]
        lines.append(f"[{ref}] {p['posted_at']} {p['text']}")
    for p in li.get("amplified_posts") or []:
        ref = f"amplified:{p['ref']}"
        refs.add(ref)
        lines.append(f"[{ref}] (reshared, not their voice) {p['text'][:300]}")
    return "\n".join(lines), refs, own


def richness_score(r: dict) -> float:
    return round(min(1.0, min(r["li_about_len"], 300) / 300 * 0.3 + min(r["ig_posts"], 12) / 12 * 0.25
                     + min(r["ig_caption_chars"], 600) / 600 * 0.2 + min(r["li_own_posts"], 5) / 5 * 0.25), 3)


def pick_voice_samples(own: dict[str, str], n: int = 3) -> list[str]:
    """Voice samples are the person's real words, chosen by code, never generated (SPEC §8.4)."""
    cands = []
    for ref, text in own.items():
        t = re.sub(r"\s+", " ", text).strip()
        if len(t) < 25:
            continue
        sent = re.split(r"(?<=[.!?])\s+", t)[0]
        cands.append(sent[:220] if len(sent) >= 25 else t[:220])
    cands = list(dict.fromkeys(cands))
    cands.sort(key=lambda s: -min(len(s), 140))
    return cands[:n]


# ---------- the calls ----------

async def _json_call(gw: Gateway, prompt: str, user: str, temp: float, images=None, sample: int = 0):
    system, ver = load_prompt(prompt)
    for attempt in range(2):  # retry once on invalid JSON
        text, _ = await gw.complete(prompt_version=ver, system=system, user=user, temperature=temp,
                                    sample=sample + attempt, json_mode=True, images=images)
        try:
            return parse_json(text)
        except Exception:
            continue
    return None


def _ref(x) -> str:
    """Models often echo the bracketed label ("[bio]", "[p:abc]"); strip it back to the raw ref."""
    return str(x).strip().strip("[]").strip()


def _norm_ev(ev) -> list[str]:
    out = []
    for e in ev if isinstance(ev, list) else [ev]:
        e = _ref(e)
        out.append(f"obs_{e}" if e.isdigit() else e)
    return out


MAIN_GROUPS = ("needs", "hobbies", "interests", "values")


def _claims_of(prof: dict, name: str) -> list[dict]:
    return [{**c, "evidence": _norm_ev(c.get("evidence") or [])}
            for c in (prof.get(name) or []) if isinstance(c, dict)]


def _as_list(x, key=None):
    if isinstance(x, dict) and key and isinstance(x.get(key), list):
        return x[key]
    if isinstance(x, dict):
        for v in x.values():
            if isinstance(v, list):
                return v
    return x if isinstance(x, list) else []


def aggregate_vision(items: list[dict]) -> dict:
    shots = Counter((i.get("shot_type") or "other") for i in items)
    n = len(items)
    return {"n_images": n, "shot_types": dict(shots),
            "group_share": round(shots.get("group", 0) / n, 2) if n else None,
            "selfie_share": round(shots.get("selfie", 0) / n, 2) if n else None,
            "activities": [i.get("activity") for i in items if i.get("activity") not in (None, "unclear")][:8],
            "settings": [i.get("setting") for i in items if i.get("setting") not in (None, "unclear")][:8]}


async def extract_person(gw: Gateway, canon: dict, images: list[tuple[str, bytes]] | None = None,
                         display_name: str | None = None, cfg=settings) -> dict:
    """canon: output of normalize_person. images: [(post_ref, jpeg bytes)]. Returns profile bundle."""
    ig, li = canon.get("instagram"), canon.get("linkedin")
    flags = list(canon["source_flags"])
    refs_all: dict[str, str] = {}   # ref -> source
    own_all: dict[str, str] = {}
    raw_obs: list[dict] = []

    if ig and (ig["posts"] or ig.get("bio")):
        text, refs, own = ig_block(ig)
        refs_all.update({r: "ig" for r in refs}); own_all.update(own)
        res = await _json_call(gw, "observer_ig", f"<data>\n{text}\n</data>", cfg.temp_extract)
        raw_obs += [{**o, "source": "ig"} for o in _as_list(res, "observations") if isinstance(o, dict)]
    if li:
        text, refs, own = li_block(li)
        refs_all.update({r: "li" for r in refs}); own_all.update(own)
        res = await _json_call(gw, "observer_li", f"<data>\n{text}\n</data>", cfg.temp_extract)
        raw_obs += [{**o, "source": "li"} for o in _as_list(res, "observations") if isinstance(o, dict)]

    vision_items: list[dict] = []
    if images:
        labelled = "\n".join(f"img{i + 1} = post {ref}" for i, (ref, _) in enumerate(images))
        res = await _json_call(gw, "vision", labelled, cfg.temp_extract, images=[b for _, b in images])
        vision_items = [i for i in _as_list(res) if isinstance(i, dict)]
        # D1: drop any per-image field that describes clothing/faith/ethnicity/health; keep the rest
        for it in vision_items:
            for k in ("activity", "setting", "objects", "mood_aesthetic"):
                if not visually_safe(str(it.get(k) or "")):
                    it[k] = "unclear"
        by_id = {f"img{i + 1}": ref for i, (ref, _) in enumerate(images)}
        for it in vision_items:
            ref = by_id.get(it.get("id"))
            act = it.get("activity")
            if ref and act and act != "unclear":
                raw_obs.append({"kind": "habit", "source": "ig", "ref": f"p:{ref}", "weight": 0.4,
                                "confidence": 0.6, "text": f"Photo shows {act}"
                                + (f", setting: {it['setting']}" if it.get("setting") not in (None, "unclear") else "")})
    vision = aggregate_vision(vision_items)

    # validate refs against the raw data, then keep each observation's source consistent with its ref
    for o in raw_obs:
        o["ref"] = _ref(o.get("ref", ""))
    kept, dropped = valid_refs(set(refs_all), raw_obs)
    observations = []
    for o in kept:
        if refs_all[str(o["ref"])] != o["source"]:
            continue
        observations.append({**o, "id": f"obs_{len(observations) + 1}"})

    # stated signals (D1): own text only, quotes verified in code
    stated: list[dict] = []
    if own_all:
        block = "\n".join(f"[{r}] {t}" for r, t in own_all.items())
        res = await _json_call(gw, "stated", f"<data>\n{block}\n</data>", cfg.temp_extract)
        items = [{**x, "ref": _ref(x.get("ref", ""))} for x in _as_list(res) if isinstance(x, dict)]
        for it in validate_stated(items,
                                  "\n\x00\n".join(own_all.values()), set(own_all)):
            if it["quote"] in own_all.get(str(it["ref"]), ""):
                stated.append({**it, "source": refs_all[str(it["ref"])]})

    # synthesis
    rich = richness_score(canon["richness"])
    obs_by_id = {o["id"]: o for o in observations}
    stats = {"richness": canon["richness"], "richness_score": rich, "source_flags": flags, "vision": vision}
    user = ("<data>\nobservations:\n" + "\n".join(
        f"{o['id']} [{o['source']}/{o['kind']}] {o['text']}" for o in observations)
        + f"\n\nstats: {stats}\n\nstated_signals: {[{k: s[k] for k in ('topic', 'value', 'quote')} for s in stated]}"
        + f"\n\nallowed tags: {VOCAB}\n</data>")
    # Small models sometimes return plain strings or empty groups; retry (fresh cache keys) while a
    # data-rich person ends up with no valid claim at all, then say so instead of saving a hollow profile.
    prof: dict = {}
    for attempt in range(4):
        got = await _json_call(gw, "synthesis", user, cfg.temp_extract, sample=attempt * 2)
        prof = got if isinstance(got, dict) else {}
        n_valid = sum(len(validate_claims(_claims_of(prof, g), obs_by_id, rich)) for g in MAIN_GROUPS)
        if n_valid or len(observations) < 8:
            break
        if attempt:
            flags.append(f"synthesis_retry_{attempt}")
    if not any(validate_claims(_claims_of(prof, g), obs_by_id, rich) for g in MAIN_GROUPS) and len(observations) >= 8:
        flags.append("synthesis_empty")
    def claims(name):
        return _claims_of(prof, name)
    for f in ("needs", "hobbies", "interests", "values", "community_and_extras", "partner_wants", "wildcards"):
        before = claims(f)
        prof[f] = validate_claims(before, obs_by_id, rich)
        if len(prof[f]) < len(before):
            flags.append(f"dropped_{len(before) - len(prof[f])}_{f}_claims")
    prof["contradictions"] = validate_contradictions(claims("contradictions"), obs_by_id)
    prof["contradictions"] = validate_claims(prof["contradictions"], obs_by_id, rich)
    prof["tags"] = clean_tags(prof.get("tags") or {})
    prof["dials"] = {k: max(0.0, min(1.0, float(v))) for k, v in (prof.get("dials") or {}).items()
                     if k in ("pace", "social_style", "tempo") and isinstance(v, (int, float))}
    prof["conversation_hooks"] = [h for h in (prof.get("conversation_hooks") or []) if isinstance(h, str)][:5]
    prof["unknowns"] = [u for u in (prof.get("unknowns") or []) if isinstance(u, str)]
    prof["stated_signals"] = stated
    raw_name = (display_name or (li or {}).get("name") or (ig or {}).get("full_name")
                or (ig or {}).get("username") or "")
    prof["identity"] = {**(prof.get("identity") or {}), "name": " ".join(str(raw_name).split()) or None}
    if not prof["identity"].get("location") and li and li.get("location"):
        prof["identity"]["location"] = ", ".join(v for v in li["location"].values() if v) or None
    ev_conf = [c["confidence"] for f in ("needs", "hobbies", "interests", "values") for c in prof[f]]
    prof["overall_confidence"] = round((sum(ev_conf) / len(ev_conf) if ev_conf else 0.0) * (0.5 + 0.5 * rich), 3)
    if canon["confidence"] == "low":
        prof["overall_confidence"] = min(prof["overall_confidence"], 0.45)
    prof["source_flags"] = flags
    prof["vision"] = vision
    prof["richness_score"] = rich

    # persona card: LLM body + code-added voice samples and unknowns
    voice = pick_voice_samples(own_all)
    card = await persona_card(gw, prof, voice, cfg)
    return {"observations": observations, "dropped_observations": len(dropped), "profile": prof,
            "persona_card": card, "voice_samples": voice, "own_text_refs": sorted(own_all)}


async def persona_card(gw: Gateway, prof: dict, voice: list[str], cfg=settings) -> str:
    system, ver = load_prompt("persona")
    system = system.replace("{{TOKENS}}", str(cfg.persona_card_tokens))
    slim = {k: prof.get(k) for k in ("identity", "work", "needs", "hobbies", "interests", "values",
                                      "communication_style", "lifestyle", "contradictions",
                                      "conversation_hooks", "stated_signals", "current_season")}
    text, _ = await gw.complete(prompt_version=ver, system=system, user=f"<data>\n{slim}\n</data>",
                                temperature=cfg.temp_extract)
    unknowns = prof.get("unknowns") or ["family", "exes", "salary", "anything not in this card"]
    # sections built by code from validated data only, so the model cannot invent them
    nl = chr(10)
    hooks = nl.join(f"- {h}" for h in prof.get("conversation_hooks", [])[:3])
    contra = nl.join(f"- {c['claim']}" for c in prof.get("contradictions", [])[:2])
    stated = nl.join(f'- {x["topic"].replace("_", " ")}: "{x["quote"]}"' for x in prof.get("stated_signals", []))
    voice_txt = nl.join(f'- "{v}"' for v in voice) or "(no usable own text; rely on the traits above)"
    parts = [text.strip()]
    if hooks:
        parts.append("HOOKS (happy to talk about):" + nl + hooks)
    if contra:
        parts.append("CONTRADICTIONS:" + nl + contra)
    if stated:
        parts.append("OPENLY STATED (their own words):" + nl + stated)
    parts.append("VOICE (their real words; match this register):" + nl + voice_txt)
    parts.append("UNKNOWNS (deflect, never invent): " + ", ".join(unknowns))
    return (nl + nl).join(parts)
