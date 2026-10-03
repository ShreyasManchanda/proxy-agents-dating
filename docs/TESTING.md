# Testing

Run the automated tests with `python -m pytest -q` (62 tests, about 2 seconds, fully offline: no network, no database, no keys).

## What the automated tests cover

| File | Covers |
|---|---|
| `test_scoring.py` | composite and tie-breaking; percentiles including a value outside the distribution; Spearman and Pearson; consensus-appeal removal (a charismatic profile must not top every list); a picky rater; a symmetric pair tagged "mutual"; one-sided tags; missing cells; sparse raters; debrief ranks; stated-value conflict detection and penalty; the slider is a pure function; a new person scored against frozen statistics without changing anyone else |
| `test_validators.py` | observation refs checked against raw data; stated quotes must be exact and on an allowed topic (including that orientation is never extracted); claims and contradictions need valid evidence; confidence caps; turn guards (length, banned phrases, quoting the persona card, echo); verdict checks including fabricated quotes; punctuation-only quote drift snapped back; the sensitive-visual filter |
| `test_dating.py` | deterministic scenario and speaker order; a full 10-turn date alternates speakers; the partner's persona card never appears in a prompt; resume continues from the last saved turn; the guard regenerates once; a fabricated verdict quote is rejected; cache hits skip the provider; backoff then fallback; daily caps; dollar budget; over-long turns are cut at a sentence boundary |
| `test_routing.py` | free providers are preferred and rotate by pair, with the paid one untouched; exhausted free quota falls to the paid one; the token-per-minute bucket delays instead of failing |
| `test_ingest.py` | only failed sources are retried; both sources failing names both links; a private Instagram degrades with a message; the image host allowlist; photo selection skips old pinned posts |
| `test_normalize.py`, `test_urls.py` | hashtag-only captions, carousel duplicates, pinned posts, reposts versus own posts, error items, missing sources; strict URL normalization and rejection of look-alike hosts and non-profile links |
| `test_baselines.py` | tag overlap, stated-signal blend at the configured weight, complement gated on shared values |

The date engine and gateway are tested with a scripted fake model, so the tests prove the *plumbing and guards*, not the quality
of any real model's output.

## What was verified by running the real thing

These are not automated; they were run once, by hand, and are recorded in [`DECISIONS.md`](DECISIONS.md) and [`RESULTS.md`](RESULTS.md).

- Real scrapes of 25 people through the three Apify actors, and everything downstream on that data.
- 12 real transcripts read in full and used to retune the prompts (the verdict calibration, the anti-mirroring instruction).
- Both live-run paths through the HTTP API: two pasted people dating each other, and one pasted person joining the demo (once against a
  made-up 8-person demo, once against the real 25), including scoring against frozen statistics and the delete button (after delete,
  every table showed zero rows for the person).
- The "already in the demo" shortcut, and the validation messages for too many, too few, bad and empty links.
- Screenshots of the landing, roster, profile, date, grid, rankings and live-progress pages with real data.
- Page-load times of published pages (about 0.2 s after the start-up prewarm).

## What is not verified

- The paste form clicked in a real browser. The API was exercised and the pages were screenshotted, but "Start the dates" was never
  clicked in a page.
- The phone layout (the headless browser used cannot render narrower than about 500 px).
- The container build and the Render deployment (Docker was not running on the development machine).
- Two people pasting at once; the daily run cap, the kill switch and the per-visitor rate limit under real use.
- The database retry on a dropped connection: it is written, but it did not fire in the run that succeeded.
- A private or missing Instagram or LinkedIn with a real account (only the logic is unit tested).
- Accessibility beyond contrast, focus styles and reduced-motion handling in the CSS; no screen-reader pass was done.
