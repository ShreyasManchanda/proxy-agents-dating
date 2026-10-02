"""URL normalizer (SPEC §6.3). Only linkedin.com/in/<id> and instagram.com/<username>."""
import re
from urllib.parse import urlsplit

_LI_ID = re.compile(r"^[A-Za-z0-9\-_%]{2,100}$")
_IG_USER = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_IG_RESERVED = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "direct"}


class BadUrl(ValueError):
    """Message is safe to show to the user."""


def _parts(raw: str) -> tuple[str, list[str]]:
    raw = (raw or "").strip()
    if not raw:
        raise BadUrl("Link is empty.")
    if "://" not in raw:
        raw = "https://" + raw
    u = urlsplit(raw)
    if u.scheme not in ("http", "https"):
        raise BadUrl("Link must start with http(s).")
    host = (u.hostname or "").lower()
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    # country subdomains like in.linkedin.com
    if host.endswith(".linkedin.com"):
        host = "linkedin.com"
    return host, [p for p in u.path.split("/") if p]


def normalize_linkedin(raw: str) -> str:
    host, segs = _parts(raw)
    if host != "linkedin.com" or len(segs) < 2 or segs[0] != "in" or not _LI_ID.match(segs[1]):
        raise BadUrl("LinkedIn link must look like linkedin.com/in/<profile-id>.")
    return f"https://www.linkedin.com/in/{segs[1].lower()}"


def normalize_instagram(raw: str) -> str:
    host, segs = _parts(raw)
    if host != "instagram.com" or not segs:
        raise BadUrl("Instagram link must look like instagram.com/<username>.")
    user = segs[0]
    if user.lower() in _IG_RESERVED or len(segs) > 1 or not _IG_USER.match(user):
        raise BadUrl("Instagram link must be a profile (instagram.com/<username>), not a post or page.")
    return f"https://www.instagram.com/{user.lower()}"
