from app.normalize.canonical import clean_caption, normalize_instagram, normalize_linkedin, normalize_person


def test_hashtag_only_caption_stripped():
    assert clean_caption(". . #a #b #c") == ""
    assert clean_caption("Sunday hike #trail") == "Sunday hike"


def test_ig_dedupe_pinned_private():
    raw = [{"username": "u", "private": False, "latestPosts": [
        {"shortCode": "a", "displayUrl": "x", "timestamp": "2024-01-02T00:00:00Z", "isPinned": True},
        {"shortCode": "b", "displayUrl": "x", "timestamp": "2024-05-01T00:00:00Z"},
        {"shortCode": "c", "displayUrl": "y", "timestamp": "2025-05-01T00:00:00Z"},
    ]}]
    posts = normalize_instagram(raw)["posts"]
    assert [p["ref"] for p in posts] == ["c", "a"]  # dup removed, sorted by time not feed order
    assert normalize_instagram([{"username": "u", "private": True, "latestPosts": [{}]}])["posts"] == []


def test_li_reposts_separated():
    prof = [{"firstName": "A", "lastName": "B", "publicIdentifier": "ab"}]
    posts = [{"id": 1, "content": "mine", "author": {"publicIdentifier": "ab"}},
             {"id": 2, "content": "theirs", "author": {"publicIdentifier": "zz"}},
             {"id": 3, "content": "rp", "repostedBy": {}, "author": {"publicIdentifier": "ab"}}]
    li = normalize_linkedin(prof, posts)
    assert [p["ref"] for p in li["own_posts"]] == [1]
    assert len(li["amplified_posts"]) == 2


def test_missing_sources_flagged_low():
    out = normalize_person(None, [{"firstName": "A"}], None)
    assert out["confidence"] == "low" and "instagram_missing" in out["source_flags"]


def test_ig_error_item_is_missing():
    assert normalize_instagram([{"error": "not_found", "errorDescription": "x"}]) is None


def test_scrub_nul_for_postgres():
    from app.service import scrub_nul
    assert scrub_nul({"a\x00": ["x\x00y", {"k": "z\x00"}], "n": 3}) == {"a": ["xy", {"k": "z"}], "n": 3}
