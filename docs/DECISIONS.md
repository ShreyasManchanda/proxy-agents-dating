# How this was built, and why

This is the thinking behind the project, written as a record rather than a sales pitch: what was decided and why,
what was measured instead of assumed, what broke on real data, and what is still not done. Dates are 2026-10-02/03.
[`SPEC.md`](../SPEC.md) is the plan that came first; this file is what happened when the plan met reality.

Contents: [1. The assignment](#1-the-assignment) · [2. Decisions made before building](#2-decisions-made-before-building) ·
[3. Choices made while building](#3-choices-made-while-building-not-in-the-spec) ·
[4. What broke, and what it taught us](#4-what-broke-on-real-data-and-what-it-taught-us) ·
[5. Estimates versus measurements](#5-estimates-versus-measurements) ·
[6. What was specified and not built](#6-specified-but-not-built) · [7. Known limits](#7-known-limits)

---

## 1. The assignment

Build an agentic dating site. Every person is represented by an agent that dates on their behalf; the agents date each
other; each person gets a ranking of who fits them best. Hard rules from the brief:

- Each person has exactly **two sources**: their public LinkedIn and their public Instagram. Nothing else is an input.
- At least **25 real people**, found by us.
- Each agent reads its person (needs, hobbies, interests, other qualities) and that appears on a **profile page**.
- The site must **work fully**: a judge pastes their own links, sees the analysis, watches agents date, reads a ranking.
- Free tiers only. Cheap models (Gemini free tier, Groq). Python, FastAPI, async, Postgres.
- Graded: the video (3 minutes, profile pages first, then rankings, agents visibly dating) above all, then the explanation
  of how it works, then the repo.

The grading order shaped the build. The video rewards two things: dates that are visibly specific, and rankings a
skeptic cannot dismiss. So the effort went into evidence, honesty and measurement more than into features.

## 2. Decisions made before building

These are in the spec's decision log; the reasoning is repeated here because it explains the shape of the code.

**Two sources only, no extra input fields (D1 in the log).** The brief allows exactly two sources, so there is no form
field for age, gender or "looking for". That rules out eligibility filtering. The pool stays open and the site says so:
*we rank compatibility, not eligibility.*

**Observations before conclusions (D3).** A small model asked to "describe this person" produces confident, generic
prose. Asked to list *atomic observations with a reference to the exact post or job line*, it is much harder to fool.
So extraction is two-stage: observers write small checkable facts, then a synthesis pass writes the profile and every
claim must cite observation ids. Code, not the model, enforces this: a claim citing an id that does not exist is dropped.

**Extraction temperature at least 0.3, determinism from caching (D7).** Zero temperature does not make small models
reliable; it makes their mistakes repeatable. Every call is cached by a hash of its input and prompt version, so a rerun
gives the same answer without pretending the model is deterministic.

**Full N×N dating (D5).** Every pair dates, so every person has 24 data points and a per-agent ranking is possible. This
is also what makes the cost and quota arithmetic the central engineering problem (see section 5).

**Rankings blend own taste and mutual fit, 60/40 (D9).** The 60/40 split is a proposal, not a finding; the UI exposes it
as a slider so a viewer can see how the lists change.

**Treat "similar attracts" and "opposites attract" as hypotheses to test (D11).** The site computes both against the
dates and reports whatever it finds. The baselines are never tuned to make either one win.

**Pasted people are ephemeral and private (D19).** A pasted person is a private row, addressed only through an
unguessable run link, with a delete button that removes every trace. This was verified: after delete, every table shows
zero rows for that person.

### The one contested decision: sensitive attributes (D12, "D1" in the spec)

The owner's position was that religion, sexuality, health and politics genuinely matter for compatibility, so excluding
them would be wrong. The spec's resolution, which the code implements exactly:

- **Built:** a *stated-signals* module. Anything a person explicitly writes in their own text (relationship intent, family
  plans, faith or practice, diet, stated political position, causes, languages, relocation) is extracted with a verbatim
  quote and a reference. These have real, tunable influence: shown on the profile, given to the agent as "openly said"
  facts, a weighted term in the baseline similarity, and a visible conflict flag with a small score penalty for a few topics.
- **Not built, anywhere:** inference of religion, orientation, gender identity, health, political affiliation, caste or
  immigration status from photos, follows, music or style. Gender identity, orientation, health, caste and immigration
  status are not extracted even when stated.

The reasoning: inference from public traces is unreliable, a wrong guess is shown on a public page about a real person, it
is special-category data about people who never entered it, and dating products rely on what people *declare*.

This was enforced in code, not just in prompts, because prompts are not guarantees:
the extractor topic allowlist rejects anything else; stated quotes must be exact substrings of the person's own text; and a
regex filter drops vision descriptions of clothing, places of worship, religious objects, ethnicity, skin and health
before they can become observations (this filter exists because the vision model really did write "traditional attire"
on a real photo during testing).

## 3. Choices made while building (not in the spec)

These were judgement calls. They are listed so a reader can disagree with them.

| Choice | Why | Status |
|---|---|---|
| "mutual" tag when the two sides' own-scores differ by at most 0.15 | Needed some threshold; no data to justify one | Mine, untuned |
| Complement baseline counts in full only when shared-values overlap reaches 0.2 | The spec said "gated on shared values"; 0.2 is arbitrary | Mine, untuned |
| Percentiles use midpoint ties; a value placed on a *frozen* distribution it is not part of uses a bounded non-member formula | The first version went negative and crashed the mutual score (see section 4) | Fixed by a test |
| Raters with fewer than 5 dates skip z-scoring and partner-effect removal | Spec said "skip adjustment below this" | As specified |
| Verdict quotes must be verbatim, but punctuation-only drift is snapped back to the exact transcript text | Models turned curly quotes and dashes into straight ones and failed validation | Mine |
| Date turns: regenerate once on a guard failure, then keep the best attempt and flag it; cut over-long turns at the last full sentence | The first cut left sentences hanging mid-word | Mine |
| One model per date: both agents in a date use the same model (chosen by hashing the pair) | Two different "brains" in one date confounds the comparison | Mine |
| Voice samples in the persona card are chosen by code from the person's real words, never generated | Spec requirement; also stops the agent inventing a voice | As specified |
| Persona card sections other than identity and traits (hooks, contradictions, stated facts, voice, unknowns) are written by code from validated data | The model invented a contradiction for someone who had none | Mine |
| A hard dollar ceiling for paid LLM calls (default $5), after which paid providers are skipped and free ones take over | Billing was enabled on the Gemini project; the failure to prevent is a runaway loop | Mine |
| Live runs capped at 5 people | A run that joins the demo is about 25 dates per person; free quotas cannot run more | Owner's choice (5 or 6) |
| Published (frozen) pools are cached in memory and pre-computed at start-up | Every API call was taking 3.5 to 5 seconds (see section 4) | Mine |

## 4. What broke on real data, and what it taught us

The synthetic fixtures passed everything. Real people found these. They are listed in the order they were found,
because the order is the lesson: almost none of these were visible without running the real thing.

1. **The Apify client changed its call signature** (`timeout_secs` became `run_timeout`; the cost cap must be a `Decimal`;
   results are objects, not dicts). Found on the very first real scrape. The offline tests could not have caught it.
2. **Postgres JSONB rejects the NUL character.** 7 of 25 people failed to store, with the unhelpful message `DBAPIError`.
   I first guessed connection limits and bounded concurrency; that was wrong. Running one failing person step by step
   with a full traceback showed the real cause. Lesson: reproduce in isolation before theorising. All stored text is now scrubbed.
3. **Hollow profiles with no warning.** For 9 of 25 people the synthesis model returned plain strings or empty groups; my code
   discarded them and saved an empty profile with confidence 0.00. The fix is a retry while a data-rich person has no valid
   claim, a stricter prompt, and a visible `synthesis_empty` flag if it still fails. Lesson: never swallow a model failure silently.
4. **The vision model described clothing as "traditional attire".** Harmless as a sentence, but it feeds a profile and
   invites exactly the inference the project promised not to make. Now filtered in code.
5. **Verdict scores were inflated.** Reading real transcripts showed a mean composite of 8.6 out of 10 and 23 of 24 verdicts
   wanting a second date, although the rubric said 5 is ordinary. Rewording the prompt as "a hard grader" brought the mean to
   5.4 but overshot on second dates (1 in 23). A separate wording for the second-date question fixed that. The final
   re-score of all 300 dates (transcripts untouched, $0.84) has mean 4.78 and 19% second dates. Lesson: calibrate on the
   real distribution, and re-score is cheap when verdicts are separate from transcripts.
6. **Agents mirrored each other.** In one audited date both agents converged on the same invented "pulse test" phrasing, which
   makes every pair look compatible. The agent prompt now says to name real differences and never adopt the partner's phrases.
   It helped; it did not eliminate it (section 7).
7. **Location lifted from a bio.** A profile showed "bom/chn" as a location because the model read it from an Instagram bio.
   LinkedIn's parsed location now wins (corrected for 10 of 25 people).
8. **"What they are after: not enough signal" was the first thing on most profiles.** Few people state what they want. The
   section is now hidden when empty and folded into one honest line.
9. **Every API call took 3.5 to 5 seconds.** The pool summary downloaded every full profile and the dates list downloaded
   every full transcript, over a remote database. Queries now fetch only the fields they show, published pools are cached
   and pre-computed at start-up, and the deploy is pinned next to the database. Published pages respond in about 0.2 s.
   Lesson: time the real pages, not just the code.
10. **A person pasted twice could crash the next paste.** Pasted people must be private rows, so the unique constraint on
    the URL pair had to go; the lookup that assumed uniqueness then raised on duplicates. Found while testing, fixed before any user hit it.
11. **The database connection occasionally dropped mid-write** during live runs. Writes now retry on a fresh connection. The
    retry has not yet fired in a successful run, so it is unproven.
12. **The free Groq quota ran out almost immediately.** Only 200 of about 3,900 batch calls ran on Groq; the gateway's
    fallback sent the rest to Gemini. This was by design, and it happened to make every date run on one model, but it was not
    what was planned. The documented cost and consistency claims are about what actually ran.

**What the audits of real transcripts found that code could not:** dates are specific and grounded in real details; agents
catch real mismatches (two people in different cities, one declined a second date for that reason); small models sometimes
borrow a detail from the partner or invent a small one.

## 5. Estimates versus measurements

The spec estimated; the build measured. The honest comparison:

| Quantity | Spec / early estimate | Measured |
|---|---|---|
| Gemini free-tier capacity | about 1,000 requests/day | **500/day** on the models this key can use (AI Studio) |
| Groq free tier | not checked | **8,000 tokens/minute and 1,000 requests/day per model** (response headers) |
| Whole batch, free tiers only | "at least 5 days" | Not feasible; billing was enabled on the Gemini project |
| Whole batch cost | about 4,200 calls | **3,915 calls, $1.95** (3,715 on Gemini) |
| Re-scoring all verdicts | not planned | $0.84 |
| One person joining the demo (25 dates) | $0.40, 3 min (extrapolated) | **$0.19, 5 min 28 s** (measured, one run) |
| Apify per person | about $0.03 | about $0.03 (total about $0.8 for 25 plus retries) |

## 6. Specified but not built

Listed plainly, because a reader checking the spec against the repo will find these.

- **Observer metrics beside each verdict** (turn-length balance, question-to-statement ratio, how often a turn builds on the
  partner's last, disclosure reciprocity). Specified as flags shown beside a verdict, never in the score. Not implemented.
- **The known-pair check** (do real friends rank each other high). Not implemented.
- **`check_pool.py` and `plan_capacity.py`.** Their jobs were done by ad-hoc queries and by measuring real limits.
- **A static JSON export of the demo as a backup.** The demo does work with every LLM service switched off, because it reads
  only the database, but it does need the database.
- **A visible queue position** for live runs. A per-run cap, a daily cap and a per-visitor rate limit exist; the queue UI does not.
- **Server-sent events in the UI.** The endpoint exists and works; the UI polls every few seconds instead.
- **Stretch extras** (fidelity check, debrief note to the person, prior-versus-posterior partner wants, a skeptic pass).
- **The LinkedIn fallback actor.** Its output shape was never verified, so it was not wired.

## 7. Known limits

- Consistency is measurable here; correctness is not. A high rank means two agents got along in this setup.
- Small models sometimes invent a small detail or borrow one from the partner. The guards reduce this; they do not remove it.
- Verdict `second_date` is now fairly rare (19%), and the grid reflects that.
- About half the pool has thin public text (12 of 25 have an empty LinkedIn About), so those profiles are sparse and low-confidence.
- None of the 25 state relationship, family, diet, faith or relocation preferences in their public text (checked by searching
  the raw text, not only by trusting the extractor), so the stated-values penalty never fires in this pool. It was tested on made-up people.
- Richer profiles score somewhat higher (r = +0.38, n = 25). Reported, not corrected.
- The order-swap check used only 10 dates, so it is weak evidence. The retest check used 60 verdicts.
- Free-tier model providers may retain submitted content; the demo people agreed to that.
- Not yet verified: the phone layout, the container build, two simultaneous live runs, and the daily cap and kill switch under load.
