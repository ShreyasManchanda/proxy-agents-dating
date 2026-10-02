"""Code-only normalizer (SPEC §6.2, §7). Raw scrape in, one canonical object out, null for missing."""
import re
from datetime import datetime, timezone

_HASHTAG_ONLY = re.compile(r"^[\s.·*\-_]*(#\w+[\s.·*\-_]*)*$")
_HASHTAG = re.compile(r"#\w+")


def _iso(v) -> str | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def clean_caption(text: str | None) -> str:
    """Strip hashtags; a caption that is only dots plus hashtags becomes empty (pitfall 5)."""
    if not text or _HASHTAG_ONLY.match(text):
        return ""
    return re.sub(r"\s+", " ", _HASHTAG.sub("", text)).strip()


def _first(items):
    return items[0] if items else None


def normalize_instagram(raw: list | None) -> dict | None:
    d = _first(raw or [])
    if not d or (d.get("error") and not d.get("username")):  # Apify error/not-found item
        return None
    private = bool(d.get("private"))
    seen: set[str] = set()
    posts = []
    for p in ([] if private else d.get("latestPosts") or []):
        # Carousel children duplicate the parent: dedupe by image URL (pitfall 3).
        urls = [u for u in [p.get("displayUrl"), *(p.get("images") or [])] if u]
        key = urls[0] if urls else p.get("shortCode") or p.get("id")
        if key in seen:
            continue
        seen.add(key)
        music = p.get("musicInfo") or {}
        original = music.get("uses_original_audio")
        posts.append({
            "ref": p.get("shortCode") or p.get("id"),
            "type": p.get("type"),
            "is_reel": p.get("productType") == "clips",
            "pinned": bool(p.get("isPinned")),  # flag; recency uses timestamp, never feed position
            "timestamp": _iso(p.get("timestamp")),
            "caption": clean_caption(p.get("caption")),
            "hashtag_count": len(p.get("hashtags") or []),
            "likes": p.get("likesCount"),
            "comments": p.get("commentsCount"),
            "tagged_count": len(p.get("taggedUsers") or []),  # counts only, never profiled
            "mention_count": len(p.get("mentions") or []),
            "song": None if original else music.get("song_name"),
            "artist": None if original else music.get("artist_name"),
            "image_url": urls[0] if urls else None,
        })
    posts.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return {
        "username": d.get("username"), "full_name": d.get("fullName"),
        "bio": (d.get("biography") or "").strip() or None,
        "followers": d.get("followersCount"), "following": d.get("followsCount"),
        "posts_count": d.get("postsCount"), "private": private, "verified": d.get("verified"),
        "is_business": d.get("isBusinessAccount"), "posts": posts,
    }


def normalize_linkedin(profile_raw: list | None, posts_raw: list | None) -> dict | None:
    d = _first(profile_raw or [])
    if not d:
        return None
    me = (d.get("publicIdentifier") or "").lower()
    own, amplified = [], []
    for p in posts_raw or []:
        author = ((p.get("author") or {}).get("publicIdentifier") or "").lower()
        item = {"ref": p.get("id") or p.get("linkedinUrl"), "text": (p.get("content") or "").strip(),
                "posted_at": _iso((p.get("postedAt") or {}).get("timestamp"))}
        # Reposts are not the person's voice (pitfall 4).
        if p.get("repostedBy") is not None or (me and author and author != me):
            amplified.append(item)
        else:
            own.append(item)
    loc = (d.get("location") or {}).get("parsed") or {}
    return {
        "name": " ".join(x for x in [d.get("firstName"), d.get("lastName")] if x) or None,
        "headline": d.get("headline"), "about": (d.get("about") or "").strip() or None,
        "location": {k: loc.get(k) for k in ("city", "state", "country")} if loc else None,
        "experience": [{"position": e.get("position"), "company": e.get("companyName"),
                        "description": e.get("description"), "start": e.get("startDate"),
                        "end": e.get("endDate")} for e in d.get("experience") or []],
        "education": [{"school": e.get("schoolName"), "degree": e.get("degree"),
                       "field": e.get("fieldOfStudy")} for e in d.get("education") or []],
        "skills": [s.get("name") for s in d.get("skills") or [] if s.get("name")],
        "own_posts": own, "amplified_posts": amplified,
    }


def richness(ig: dict | None, li: dict | None) -> dict:
    """Metrics that drive confidence and check_pool.py (SPEC §7)."""
    posts = (ig or {}).get("posts") or []
    return {
        "li_about_len": len((li or {}).get("about") or ""),
        "li_own_posts": len((li or {}).get("own_posts") or []),
        "ig_posts": len(posts),
        "ig_caption_chars": sum(len(p["caption"]) for p in posts),
        "ig_private": bool((ig or {}).get("private")),
        "has_li": li is not None, "has_ig": ig is not None,
    }


def normalize_person(ig_raw, li_raw, li_posts_raw) -> dict:
    ig, li = normalize_instagram(ig_raw), normalize_linkedin(li_raw, li_posts_raw)
    flags = []
    if ig is None:
        flags.append("instagram_missing")
    elif ig["private"]:
        flags.append("instagram_private")
    if li is None:
        flags.append("linkedin_missing")
    elif not li["about"]:
        flags.append("linkedin_about_empty")
    low = ig is None or li is None or bool(ig and ig["private"])
    return {"instagram": ig, "linkedin": li, "richness": richness(ig, li),
            "source_flags": flags, "confidence": "low" if low else "normal"}
