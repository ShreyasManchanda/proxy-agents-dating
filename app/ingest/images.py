"""Image selection + safe download (SPEC §6.5)."""
import asyncio
import io
from urllib.parse import urlsplit

import httpx
from PIL import Image

from app.config import settings

# Instagram/LinkedIn CDN suffixes. Anything else is refused, including redirects to other hosts.
ALLOWED_HOST_SUFFIXES = (".cdninstagram.com", ".fbcdn.net", ".licdn.com")
MAX_BYTES = 8_000_000
MAX_SIDE = 640


def host_allowed(url: str) -> bool:
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host.endswith(s) for s in ALLOWED_HOST_SUFFIXES)


def select_images(posts: list[dict], n: int | None = None) -> list[dict]:
    """First image of each own, non-duplicate post: mix recent and most-liked, skip old pinned
    posts unless nothing else exists. `posts` are normalized IG posts (already deduped)."""
    n = n or settings.images_per_person
    usable = [p for p in posts if p.get("image_url")]
    fresh = [p for p in usable if not p["pinned"]] or usable
    recent = sorted(fresh, key=lambda p: p["timestamp"] or "", reverse=True)
    liked = sorted(fresh, key=lambda p: p.get("likes") or 0, reverse=True)
    out, seen = [], set()
    # alternate recent / most-liked until full
    for a, b in zip(recent, liked):
        for p in (a, b):
            if p["ref"] not in seen and len(out) < n:
                seen.add(p["ref"])
                out.append(p)
    return out


def _resize(data: bytes) -> bytes:
    im = Image.open(io.BytesIO(data))
    im.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))
    im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


async def fetch_image(client: httpx.AsyncClient, url: str) -> bytes | None:
    """Download one allowlisted image. Redirects are followed manually and re-checked per hop."""
    for _ in range(3):
        if not host_allowed(url):
            return None
        try:
            async with client.stream("GET", url, follow_redirects=False, timeout=20) as r:
                if r.is_redirect:
                    url = str(r.headers.get("location") or "")
                    continue
                if r.status_code != 200:
                    return None
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        return None
            return await asyncio.to_thread(_resize, bytes(buf))
        except Exception:  # bad image, timeout, network: skip this image
            return None
    return None


async def download_selected(posts: list[dict]) -> list[tuple[str, bytes]]:
    chosen = select_images(posts)
    async with httpx.AsyncClient() as client:
        got = await asyncio.gather(*(fetch_image(client, p["image_url"]) for p in chosen))
    return [(p["ref"], b) for p, b in zip(chosen, got) if b]
