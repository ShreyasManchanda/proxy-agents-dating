# Proxy: agents that date for you

Paste a LinkedIn and a public Instagram per person. An agent reads them, builds a profile whose every claim links to its
evidence, then dates every other agent on that person's behalf. **The ranking comes from the dates, not the profiles.**

> Live site, demo and video links: _to be added when published._ Everything below runs locally today.

## At a glance

| | |
|---|---|
| The pool | 25 real people (public LinkedIn + public Instagram), all pairs dated: **300 dates, 0 failed** |
| A date | two agents, one model call per turn, 10 turns (intro, deeper disclosure, a friction scenario), two blind verdicts |
| Cost | **$1.95** of LLM spend for the whole batch; one person joining the demo is about **$0.19 and 5.5 minutes** |
| Tests | 62 offline tests; real-data checks are documented in [docs/TESTING.md](docs/TESTING.md) |
| Stack | Python, FastAPI, asyncio, Postgres (Supabase); React + Vite + TypeScript; Apify; Gemini 3.5 Flash-Lite and Groq |

What makes it different from a prompt and a vibe:

- **Evidence you can click.** A profile claim opens to the observations behind it, and each observation to the post or job line it came from.
  Code drops any claim whose evidence does not exist.
- **Dates you can audit.** The partner's profile is never in an agent's prompt, and each verdict's quote must be a real line from the transcript.
- **A ranking built not to be gamed by popularity.** Each agent's scale is normalised, consensus appeal is removed, and no person tops every list.
- **Honest reporting.** Similar-versus-opposite came out weak (+0.10 / +0.12) and the site says so. Consistency checks are on the page.

Results: [docs/RESULTS.md](docs/RESULTS.md). Reasoning, mistakes and measurements: [docs/DECISIONS.md](docs/DECISIONS.md).

## How it works

```
paste / seed URLs
  -> Ingest      3 Apify actors in parallel -> raw JSON in Postgres, photos downloaded and resized
  -> Normalize   code only: dedupe, own words vs reposts, hashtag spam, flags, richness
  -> Extract     observers (Instagram, LinkedIn, vision) -> validated observations
                 stated-signals pass (verbatim quotes) -> synthesis (claims cite observation ids) -> persona card
  -> Dates       agents alternate turns -> blind verdicts (quote must be verbatim) -> per-person debrief ranking
  -> Scoring     pure functions: per-rater z-scores, remove consensus appeal, percentiles, own taste blended with mutual fit
  -> API + UI    FastAPI serves a React app: roster, profiles, transcripts, dating grid, rankings with a slider
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### How Instagram and LinkedIn are scraped

Public pages only, through Apify actors called with an API token: `apify/instagram-scraper` (profile plus the latest 12 posts, reel songs,
tag counts), `harvestapi/linkedin-profile-scraper` and `harvestapi/linkedin-profile-posts`. No cookies, no login, no browser automation
of our own. Raw output is stored untouched and normalised on read, so a provider change never forces a rescrape. A pasted URL can trigger
only those three scrapes, and URLs are strictly validated (`linkedin.com/in/<id>` and `instagram.com/<user>` only). Photo URLs expire, so
photos are downloaded at ingest from an allowlist of Instagram and LinkedIn CDN hosts and stored in the database.

### What the agents will and will not use

Things a person **states in their own words** count: relationship intent, family plans, faith or practice, diet, a political position,
causes, languages, relocation. Each is shown with its exact quote, and a few can raise a visible conflict flag with a small score penalty.
**Nothing is inferred** about religion, sexual orientation, gender identity, health, politics, caste or immigration status from photos,
follows, music or style. That is enforced in code (topic allowlist, quotes must be exact substrings, a filter on vision output), not only in
prompts. Why: inference from public traces is unreliable, a wrong guess on a public page about a real person is harmful, and dating
products rely on what people declare. See decision D1 in [docs/DECISIONS.md](docs/DECISIONS.md).

## Run it locally

Prerequisites: Python 3.12, Node 22, a Postgres database (a free Supabase project works), and API keys for Apify, Gemini and Groq.

```bash
cp .env.example .env              # fill in the four values
pip install -r requirements.txt
python -m scripts.init_db         # creates the 11 tables, row-level security on, no public policies
cd web && npm install && npm run build && cd ..
uvicorn app.main:app              # app and API on http://127.0.0.1:8000
python -m pytest -q               # 62 tests, offline
```

With an empty database the site loads but there is no demo yet. To build a pool from your own consenting people:

```bash
python -m scripts.seed_pool people.xlsx            # validate links, write pool.csv (columns: linkedin, instagram)
python -m scripts.seed_pool pool.csv --ingest      # scrape and read everyone (spends Apify credit)
python -m scripts.run_demo25 --limit-pairs=6       # a few dates first: read the transcripts before trusting prompts
python -m scripts.run_demo25                       # the full batch; resumable
python -m scripts.diagnostics                      # test-retest and order-swap checks
python -m scripts.run_demo25 --publish             # freeze the pool and make it the public demo
```

`pool.csv` and spreadsheets are gitignored on purpose: they contain real people's links. A synthetic fixture
(`fixtures/synthetic.py`, `python -m scripts.run_synthetic 4`) lets you try the whole pipeline without any real person.

Pasting people on the site: by default a pasted person is added to the demo (their own profile, 25 dates, and a ranking); untick that to
date only the pasted people (at least two). Live runs are limited to **5 people**. Pasted people are private to the run link and can be
deleted there. Deploying: [docs/DEPLOY.md](docs/DEPLOY.md).

## Documentation

| Document | What it is |
|---|---|
| [docs/DECISIONS.md](docs/DECISIONS.md) | The thinking: decisions and reasons, choices made while building, what broke on real data, estimates versus measurements, what was not built |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stages, modules, scoring formulas, the LLM gateway, data model, API |
| [docs/RESULTS.md](docs/RESULTS.md) | What was measured on the 25-person pool |
| [docs/TESTING.md](docs/TESTING.md) | What the tests cover, what was verified by hand, what is not verified |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Environment, Render free tier, Supabase, post-deploy checks |
| [docs/DELIVERABLES.md](docs/DELIVERABLES.md) | The short write-ups and the video script |
| [SPEC.md](SPEC.md) | The original build spec this implements |
| [PRODUCT.md](PRODUCT.md) | Users, tone and design principles for the interface |
| [PROGRESS.md](PROGRESS.md) | Chronological build log |

## Honest limits

- Consistency is measurable here; **correctness is not**. A high rank means two agents got along in this setup, not that two people would.
  Attraction cannot be measured from two public profiles.
- Agents are told to speak only from their persona card and to deflect on anything else. Small models still sometimes borrow a detail from the
  partner or invent a small one. Read the transcripts.
- About half the pool has thin public text, so those profiles are sparse and low-confidence, and richer profiles score somewhat higher (r = +0.38).
- None of the 25 people state relationship, family, diet, faith or relocation preferences publicly, so the stated-values penalty never fires in
  this pool; it was tested on made-up people.
- Several parts of the spec were not built (observer metrics, known-pair check, a queue UI, a static export). The full list is in
  [docs/DECISIONS.md](docs/DECISIONS.md#6-specified-but-not-built).
- Free-tier model providers may retain submitted content. Everyone in the demo pool agreed to that.
- Not verified: the phone layout, the container build, concurrent live runs. See [docs/TESTING.md](docs/TESTING.md).
