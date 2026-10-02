import pytest

from app.ingest.urls import BadUrl, normalize_instagram, normalize_linkedin


@pytest.mark.parametrize("raw,want", [
    ("https://www.linkedin.com/in/Jane-Doe/?utm=x#a", "https://www.linkedin.com/in/jane-doe"),
    ("linkedin.com/in/jane", "https://www.linkedin.com/in/jane"),
    ("https://in.linkedin.com/in/jane/", "https://www.linkedin.com/in/jane"),
])
def test_linkedin_ok(raw, want):
    assert normalize_linkedin(raw) == want


@pytest.mark.parametrize("raw", ["", "https://linkedin.com/company/x", "https://evil.com/in/jane",
                                 "https://linkedin.com.evil.com/in/jane", "ftp://linkedin.com/in/j"])
def test_linkedin_bad(raw):
    with pytest.raises(BadUrl):
        normalize_linkedin(raw)


@pytest.mark.parametrize("raw,want", [
    ("https://m.instagram.com/Some.User/?hl=en", "https://www.instagram.com/some.user"),
    ("instagram.com/abc/", "https://www.instagram.com/abc"),
])
def test_instagram_ok(raw, want):
    assert normalize_instagram(raw) == want


@pytest.mark.parametrize("raw", ["https://instagram.com/p/XYZ/", "https://instagram.com/explore",
                                 "https://instagram.com/a/b", "https://twitter.com/a"])
def test_instagram_bad(raw):
    with pytest.raises(BadUrl):
        normalize_instagram(raw)
