"""Ingest orchestration with the §6.4 failure table. Every failure yields a user-visible message."""
from collections.abc import Awaitable, Callable

from app.ingest.apify import ScrapeResult, scrape_person
from app.normalize.canonical import normalize_person

Scraper = Callable[..., Awaitable[list[ScrapeResult]]]


class IngestError(Exception):
    """Both sources failed. Message names which link failed and why."""


def _by_source(results: list[ScrapeResult]) -> dict[str, ScrapeResult]:
    return {r.source: r for r in results}


async def ingest_pair(li_url: str, ig_url: str, scraper: Scraper = scrape_person) -> dict:
    """Returns {'raw': [ScrapeResult...], 'person': canonical, 'messages': [user-facing str]}."""
    results = await scraper(li_url, ig_url)
    src = _by_source(results)

    # Provider failure: retry only the failed sources once (a private IG is a clean result, not a failure).
    failed = tuple(s for s in ("ig", "li", "li_posts") if not src[s].ok)
    if failed:
        for r in await scraper(li_url, ig_url, sources=failed):
            if r.ok:
                src[r.source] = r
    # LinkedIn fallback actor (apimaestro/linkedin-profile-detail) is unverified (§6): not wired.
    # Without a mapper we degrade to Instagram only per §6.4.

    ig, li = src["ig"], src["li"]
    messages = []
    if not ig.ok and not li.ok:
        raise IngestError(
            f"Could not read either link. Instagram ({ig_url}): {ig.error}. LinkedIn ({li_url}): {li.error}."
        )
    if not ig.ok:
        messages.append(f"Instagram link couldn't be read ({ig.error}); profile uses LinkedIn only, low confidence.")
    if not li.ok:
        messages.append(f"LinkedIn link couldn't be read ({li.error}); profile uses Instagram only, low confidence.")

    person = normalize_person(
        ig.payload if ig.ok else None,
        li.payload if li.ok else None,
        src["li_posts"].payload if src["li_posts"].ok else None,
    )
    flags = person["source_flags"]
    if "instagram_private" in flags:
        messages.append("Instagram account is private, so no posts were readable. Profile uses LinkedIn only, low confidence.")
    if "linkedin_about_empty" in flags:
        messages.append("LinkedIn 'About' is empty: low text signal on affected traits.")
    return {"raw": list(src.values()), "person": person, "messages": messages}
