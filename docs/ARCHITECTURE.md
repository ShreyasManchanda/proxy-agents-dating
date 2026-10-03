# Architecture

One deployable service: a FastAPI app that serves a built React app and a JSON API, backed by Postgres. The long jobs
(scraping, extraction, dating) run as asyncio tasks, either from a script on a laptop (the 25-person batch) or inside the
server (a pasted run). Nothing here needs a queue or a second process.

```
paste / seed URLs
   |
   v
[ingest]    3 Apify actors in parallel  ->  raw_scrape (JSONB, untouched)  +  8 photos downloaded and resized
   |
   v
[normalize] code only: dedupe, own words vs reposts, hashtag spam, flags, richness metrics
   |
   v
[extract]   observers (Instagram, LinkedIn, vision) -> validated observations
            stated-signals pass (verbatim quotes) -> synthesis (claims cite observation ids) -> persona card
   |
   v
[dates]     two agents alternate turns (one LLM call per turn) -> two blind verdicts -> per-person debrief ranking
   |
   v
[scoring]   pure functions: z-scores per rater -> remove consensus appeal -> percentiles -> own / mutual / final
   |
   v
[api + ui]  FastAPI routes, React app, frozen-pool cache
```

## Repository map

| Path | What lives there |
|---|---|
| `app/ingest/` | `apify.py` actor calls with a per-run spend cap; `urls.py` strict URL normalizer; `images.py` photo selection and host-allowlisted download; `pipeline.py` retry and failure messages |
| `app/normalize/canonical.py` | raw scrape to one canonical object per person; pitfalls handled in code (carousel duplicates, pinned posts, reposts, hashtag-only captions, private accounts, error items) |
| `app/extract/` | `pipeline.py` observers, vision, stated signals, synthesis, persona card; `validators.py` every check on model output; `vocab.py` the fixed tag vocabulary |
| `app/dating/runner.py` | the date engine: phases, scenarios, turn guards, verdicts, resume |
| `app/scoring/core.py` | all of section 11 of the spec as pure functions |
| `app/baselines/core.py` | similarity and complement baselines |
| `app/llm/` | `gateway.py` cache, rate limits, routing, budget; `providers.py` Gemini (with images) and Groq adapters |
| `app/service.py`, `app/jobs.py` | orchestration over the database; the live-run job |
| `app/api/routes.py`, `app/main.py` | HTTP API, caching of published pools, start-up prewarm, serving the built app |
| `app/db/` | SQLAlchemy models (11 tables) and the connection pool |
| `prompts/` | every prompt as a versioned file (the version is a hash of the text) |
| `scripts/` | `init_db`, `seed_pool`, `run_demo25`, `rescore_verdicts`, `diagnostics`, `rebuild_profiles`, smoke tests |
| `web/` | React + Vite + TypeScript front end, plain CSS tokens |
| `fixtures/synthetic.py` | made-up people in Apify's output shape, for tests and development only |
| `tests/` | 62 offline tests |

## Stage details

### Ingest
Three Apify actors per person, run in parallel with an explicit `maxTotalChargeUsd`: `apify/instagram-scraper` (profile
plus the latest 12 posts, reel songs, tag counts), `harvestapi/linkedin-profile-scraper` and
`harvestapi/linkedin-profile-posts`. No cookies and no login. Raw output is stored untouched and normalized on read, so a
provider change never forces a rescrape. A failed source is retried once (only the failed one), then the profile degrades
to the other source with a visible message; an empty posts result is valid and is not retried. Image URLs expire, so photos are
downloaded at ingest from an allowlist of Instagram and LinkedIn CDN hosts (redirects are re-checked per hop) and stored in
Postgres.

### Extract
Prompts are in `prompts/*.md`, each prefixed with the same header telling the model that text inside `<data>` tags is
untrusted web content and that it must never infer sensitive attributes. All scraped text and all partner text is wrapped.

1. **Observers** (Instagram, LinkedIn, vision) emit `{kind, text, ref, weight, confidence}`. Code checks every `ref` against
   the raw data and drops observations whose ref does not exist or whose source does not match the ref.
2. **Stated signals** scan only the person's own text. A quote must be an exact substring of one text block; the topic must
   be on the allowlist; conflict-capable topics carry a normalized enum so conflicts are detected in code.
3. **Synthesis** reads only observations and computed stats. Every claim is `{claim, evidence, confidence}`; claims citing
   missing ids are dropped, confidence is capped by evidence count and profile richness, contradictions must cite one
   observation from each source, and tags are cleaned to a fixed vocabulary. If a data-rich person ends up with no valid claim,
   synthesis is retried, then flagged.
4. **Persona card**: the model writes identity and traits only; code appends hooks, contradictions, stated facts, voice
   samples (the person's real words) and the list of things the agent must deflect on.

### Dates
Per turn the prompt contains only that agent's persona card, the rules, the current phase and the transcript so far. The
partner's card is never present (there is a test for this). Turn plan is 3 intro, 4 escalating disclosure, 3 friction scenario
(one of eight, chosen by hashing the pair); speaker order is also a hash of the pair. Guards check word count, banned phrases,
verbatim quoting of the persona card and echoing of the partner's last turn; on failure the turn is regenerated once. The
transcript is saved after every turn, so a crashed date resumes from its last saved turn. Verdicts are blind, sampled twice, and
their quote must appear verbatim in the transcript. Finally one call per person ranks its 24 partners from the one-line
reasons in its verdicts.

### Scoring (`app/scoring/core.py`)
1. composite per verdict sample: mean of six dimensions (candor and ease, mutual enjoyment, attentiveness, positivity,
   coordination, perceived similarity), averaged over samples; `second_date` only breaks ties
2. per-rater z-score (raters with fewer than 5 dates skip this)
3. subtract each target's partner effect (mean z across raters), removing consensus appeal (Social Relations Model)
4. percentile within the rater; the debrief rank is converted the same way
5. `own = mean(composite percentile, rank percentile)`
6. `mutual = sqrt(own_ab * own_ba)`
7. `final = max(0, w * own + (1 - w) * mutual - conflict_penalty)`, w adjustable from the UI without any LLM call
8. tags "mutual", "you like them more", "they like you more"

A **new person joining the demo** is scored against the demo's *frozen* statistics (rater means and SDs, partner effects,
adjusted-score distributions) so the 25 members' own rankings never change. The demo members' view of a new person has
no debrief component (they never ranked them), and the UI labels it as based on date scores only.

### LLM gateway (`app/llm/gateway.py`)
Cache by hash of input and prompt version (in memory plus the `llm_cache` table). A token bucket per provider and a
tokens-per-minute bucket for Groq. Exponential backoff on 429. Named routes: date turns try the free Groq models first (a
model chosen per pair), verdicts and extraction try Gemini Flash-Lite first, each falls back to the other. Real token counts
from the providers are priced against `config.prices`; once `llm_budget_usd` is spent, paid providers are skipped. Daily call
caps keep the free providers under their limits.

### Data model
`person`, `raw_scrape`, `image`, `observation`, `profile`, `date`, `verdict`, `debrief`, `pool`, `pool_member`, `llm_cache`.
Scores are derived on request from verdicts and debriefs, never stored. Row-level security is enabled on every table with no
policies, so the database's public REST interface exposes nothing; the backend connects as the owner.

## API

| Method and path | Purpose |
|---|---|
| `GET /api/config` | paste on or off, live runs left today, the demo's token |
| `POST /api/pools` | start a run; returns a token, or a redirect when everyone pasted is already in the demo |
| `GET /api/pools/{token}` | pool summary, phase, people with status and confidence |
| `GET /api/pools/{token}/people/{id}` | the profile with evidence |
| `GET /api/pools/{token}/dates`, `.../dates/{id}` | the grid; one transcript with verdicts |
| `GET /api/pools/{token}/rankings?own_weight=` | per-person ranked lists with every number |
| `GET /api/pools/{token}/diagnostics` | similar-vs-opposite test, consistency checks, richness correlation |
| `GET /api/pools/{token}/events` | server-sent events (the UI currently polls instead) |
| `DELETE /api/pools/{token}/people/{id}` | remove a pasted person and everything about them |
| `GET /health` | health check |

Access control is the token in the URL. Pasting is rate limited per visitor, capped per day, limited to 5 people per run, and can
be switched off with `PASTE_ENABLED=false` while the demo stays browsable.

## Front end
React, TypeScript and Vite, built to `web/dist` and served by FastAPI (any non-API path returns the app, so deep links work).
Design context is in [`PRODUCT.md`](../PRODUCT.md): light theme, one bottle-green accent, Geist type, claims that expand to
their evidence, transcripts with the verdict's quoted moment highlighted, a dating grid shaded by observed score range, and a
rankings page with the own-versus-mutual slider.

## Configuration
Every tunable is in `app/config.py` (temperatures, turn plan, scoring weights, model names, prices, budgets, limits). Secrets
come only from environment variables; see `.env.example`.
