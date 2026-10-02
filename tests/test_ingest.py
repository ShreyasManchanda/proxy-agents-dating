import pytest

from app.ingest.apify import ScrapeResult
from app.ingest.images import host_allowed, select_images
from app.ingest.pipeline import IngestError, ingest_pair

LI, IG = "https://www.linkedin.com/in/a", "https://www.instagram.com/a"
IG_OK = [{"username": "a", "private": False, "latestPosts": [
    {"shortCode": "p1", "displayUrl": "https://x.cdninstagram.com/1.jpg", "timestamp": "2025-01-01T00:00:00Z"}]}]
LI_OK = [{"firstName": "A", "about": "hi", "publicIdentifier": "a"}]


def fake(plan):
    """plan: list of dicts source->ScrapeResult per call; records requested sources."""
    calls = []

    async def scraper(li, ig, sources=("ig", "li", "li_posts")):
        calls.append(sources)
        return [plan[min(len(calls) - 1, len(plan) - 1)][s] for s in sources]
    scraper.calls = calls
    return scraper


def R(src, ok, payload=None, err=None):
    return ScrapeResult(src, "t", ok, payload, err)


@pytest.mark.asyncio
async def test_retry_only_failed_sources_then_success():
    s = fake([
        {"ig": R("ig", False, err="timeout"), "li": R("li", True, LI_OK), "li_posts": R("li_posts", True, [])},
        {"ig": R("ig", True, IG_OK)},
    ])
    out = await ingest_pair(LI, IG, s)
    assert s.calls == [("ig", "li", "li_posts"), ("ig",)]
    assert out["person"]["instagram"] is not None


@pytest.mark.asyncio
async def test_both_failed_names_both_links():
    bad = {k: R(k, False, err="boom") for k in ("ig", "li", "li_posts")}
    with pytest.raises(IngestError) as e:
        await ingest_pair(LI, IG, fake([bad]))
    assert IG in str(e.value) and LI in str(e.value)


@pytest.mark.asyncio
async def test_private_ig_degrades_with_message():
    priv = [{"username": "a", "private": True}]
    s = fake([{"ig": R("ig", True, priv), "li": R("li", True, LI_OK), "li_posts": R("li_posts", True, [])}])
    out = await ingest_pair(LI, IG, s)
    assert out["person"]["confidence"] == "low"
    assert any("private" in m for m in out["messages"])


def test_host_allowlist():
    assert host_allowed("https://scontent.cdninstagram.com/a.jpg")
    assert not host_allowed("http://scontent.cdninstagram.com/a.jpg")
    assert not host_allowed("https://cdninstagram.com.evil.com/a.jpg")
    assert not host_allowed("https://evil.com/x.jpg")


def test_select_images_skips_pinned_and_caps():
    posts = [{"ref": str(i), "image_url": f"u{i}", "pinned": i == 0, "timestamp": f"2025-01-{i + 1:02d}",
              "likes": i} for i in range(12)]
    got = select_images(posts, 8)
    assert len(got) == 8 and "0" not in {p["ref"] for p in got}
    only_pinned = [{"ref": "z", "image_url": "u", "pinned": True, "timestamp": None, "likes": 1}]
    assert [p["ref"] for p in select_images(only_pinned)] == ["z"]
