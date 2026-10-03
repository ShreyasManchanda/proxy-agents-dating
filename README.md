# Proxy: agents that date for you

Paste a LinkedIn and a public Instagram per person. An agent reads them, builds an evidence-cited profile, then
dates every other agent on that person's behalf. The ranking comes from the dates, not the profiles.

- **Live site:** _add URL_  ·  **Demo (already run, works with live APIs off):** _add URL_  ·  **Video:** _add URL_
- Full design and decisions: [`SPEC.md`](SPEC.md). Build status: [`PROGRESS.md`](PROGRESS.md).

## How it works

```
paste / seed URLs
  -> Ingest      3 Apify actors in parallel -> raw JSON in Postgres, photos downloaded and resized
  -> Normalize   code only: dedupe, reposts vs own words, hashtag spam, flags, richness
  -> Extract     observers (Instagram, LinkedIn, vision) -> validated observations
                 stated-signals pass (quotes verified in code) -> synthesis (every claim cites observation ids)
                 -> persona card (voice samples are the person's real words, chosen by code)
  -> Dates       two agents alternate turns, one LLM call per turn, never one model writing both sides;
                 intro -> deeper disclosure -> a friction scenario; guards on length, echo and persona quoting
  -> Verdicts    each agent writes a blind verdict; its quote must be a verbatim line of the transcript
  -> Scoring     pure functions: per-rater z-scores, removal of consensus appeal, percentile map,
                 own taste blended with mutual fit, small visible penalty for stated-value conflicts
  -> API + SSE   FastAPI serves the React app and the JSON the app reads
```

### How Instagram and LinkedIn are scraped

Public pages only, through Apify actors called with an API token. No cookies, no login, no browser automation of ours.
`apify/instagram-scraper` (profile plus the latest 12 posts, reel songs, tag counts), `harvestapi/linkedin-profile-scraper`
(experience, education, skills) and `harvestapi/linkedin-profile-posts`. Raw output is stored untouched and normalised on
read, so a change in the provider never forces a rescrape. A pasted URL can trigger only those three scrapes. Image URLs
expire, so photos are downloaded at ingest from an allowlist of Instagram and LinkedIn CDN hosts (redirects are re-checked
per hop) and stored in the database.

### What the agents will and will not use

Self-declared text counts: relationship intent, family plans, faith or practice, diet, stated politics, causes,
languages, relocation. Each is shown with its exact quote. Three of them can raise a visible conflict flag with a small
score penalty, and the weight is a config constant. **Nothing is inferred** about religion, sexual orientation, gender
identity, health, politics, caste or immigration status from photos, follows, music or style, and a code filter drops
visual descriptions that invite it (see decision D1 in the spec).

## Run it

```
cp .env.example .env            # fill DATABASE_URL, APIFY_TOKEN, GEMINI_API_KEY, GROQ_API_KEY
pip install -r requirements.txt
python -m scripts.init_db       # creates tables, row-level security on, no public policies
cd web && npm install && npm run build && cd ..
uvicorn app.main:app            # serves the API and the built app on :8000
```

Seeding a pool (real people stay out of the repo; `pool.csv` and spreadsheets are gitignored):

```
python -m scripts.seed_pool datings.xlsx             # validate links, write pool.csv
python -m scripts.seed_pool pool.csv --ingest        # scrape and read everyone
python -m scripts.run_demo25 --limit-pairs=6         # a few dates to read before freezing prompts
python -m scripts.run_demo25 --publish               # the full batch, then freeze and publish
python -m pytest -q                                  # unit tests, all offline
```

Models, prices, rate limits and the dollar ceiling are in `app/config.py`. Date turns run on free Groq models, while
verdicts, extraction and vision run on Gemini Flash-Lite; if the dollar budget is spent, paid calls stop and Groq
takes over.

## Pasting your own people

By default a pasted person is added to the 25-person demo: they get a profile, 25 dates and their own ranking, and anyone
pasted with them also dates each other. Untick that to date only the pasted people (at least two). Live runs are limited to
**5 people**, because a run that joins the demo is about 25 dates per person and the model providers are free or capped.
Someone who is already in the demo opens instantly. Pasted people are private to the run link and can be deleted there.

## Honest limits

- Consistency can be measured here; correctness cannot. A high rank means two agents got along in this setup, not
  that two people would. Attraction cannot be measured from two public profiles.
- Agents are told to speak only from the persona card and to deflect on anything else. Small models still sometimes
  borrow a detail from the partner or invent a small one. Read the transcripts.
- Public profiles are thin. Where text is sparse the profile says so and confidence is capped.
- Free tiers of third-party AI providers may retain submitted content. Everyone in the demo pool should have agreed to that.
- With a small group the "similar versus opposite" statistics move a lot; they are reported, never tuned.
