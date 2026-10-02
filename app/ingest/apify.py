"""Apify actor calls (SPEC §6). Raw output is returned untouched for raw_scrape."""
import asyncio
from datetime import timedelta
from decimal import Decimal
from dataclasses import dataclass

from apify_client import ApifyClientAsync

from app.config import settings

IG_ACTOR = "apify/instagram-scraper"
LI_PROFILE_ACTOR = "harvestapi/linkedin-profile-scraper"
LI_POSTS_ACTOR = "harvestapi/linkedin-profile-posts"


@dataclass
class ScrapeResult:
    source: str  # ig | li | li_posts
    provider: str
    ok: bool
    payload: list | None = None
    error: str | None = None
    cost_usd: float = 0.0  # from the Apify run object, for per-person spend logging


def _get(run, snake: str, camel: str):
    """apify-client v3 returns model objects; older versions returned dicts. Accept both."""
    if isinstance(run, dict):
        return run.get(camel)
    return getattr(run, snake, None)


async def _run(client: ApifyClientAsync, actor: str, run_input: dict, source: str) -> ScrapeResult:
    try:
        run = await client.actor(actor).call(
            run_input=run_input,
            max_total_charge_usd=Decimal(str(settings.apify_max_charge_per_run_usd)),
            run_timeout=timedelta(seconds=120),
        )
        if run is None:
            return ScrapeResult(source, actor, False, None, "run did not finish")
        items = (await client.dataset(_get(run, "default_dataset_id", "defaultDatasetId")).list_items()).items
        # Posts may legitimately be empty (person never posts); that is not a failure and not retried.
        ok = bool(items) or source == "li_posts"
        return ScrapeResult(source, actor, ok, items, None if ok else "empty result",
                            float(_get(run, "usage_total_usd", "usageTotalUsd") or 0.0))
    except Exception as e:  # provider timeout etc: caller retries once per §6.4
        return ScrapeResult(source, actor, False, None, f"{type(e).__name__}: {e}")


async def scrape_person(li_url: str, ig_url: str,
                        sources: tuple[str, ...] = ("ig", "li", "li_posts")) -> list[ScrapeResult]:
    """Run the requested primary actors in parallel for one person."""
    client = ApifyClientAsync(settings.apify_token)
    jobs = {
        "ig": (IG_ACTOR, {"directUrls": [ig_url], "resultsType": "details", "resultsLimit": 1}),
        "li": (LI_PROFILE_ACTOR, {"profileScraperMode": "Profile details no email ($4 per 1k)",
                                  "queries": [li_url]}),
        "li_posts": (LI_POSTS_ACTOR, {"targetUrls": [li_url], "maxPosts": settings.li_posts}),
    }
    return list(await asyncio.gather(*(_run(client, *jobs[s], s) for s in sources)))
