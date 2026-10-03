# Results

What was measured on the real pool of 25 people. These are aggregates only; the people agreed to be in the demo and no
personal detail is repeated here. How each number was produced is in [`DECISIONS.md`](DECISIONS.md) and the scripts named below.

## The run

| | |
|---|---|
| People | 25 real people, each a public LinkedIn plus a public Instagram, found by the owner, who attests they agreed |
| Dates | 300 (every pair), 0 failed |
| Rankings | each person ranks the other 24 |
| Models | Gemini 3.5 Flash-Lite (almost all calls), three Groq open models (about 200 calls before the free quota ran out) |
| Date format | 10 turns per date: 3 intro, 4 escalating disclosure, 3 friction scenario; two blind verdicts per date, each sampled twice |
| LLM spend | **$1.95** for the batch, $0.84 to re-score all verdicts, about $0.10 for the consistency checks |
| Apify spend | about $0.8 for 25 people plus retries |

## Profiles

- 12 of 25 people have an empty LinkedIn About, so their profiles have less text to read.
- Profile confidence ranges from 0.16 to 0.68; the people with the least public text score lowest, as intended.
- **No one states relationship, family, diet, faith or relocation preferences in their public text.** Checked two ways: the
  extractor returned nothing for all 25, and a keyword search of the raw text found only false positives ("looking forward
  to", "single post", "party"). So the stated-values penalty never fires in this pool.

## The scoring

| Verdict composite (out of 10) | after re-scoring |
|---|---|
| mean | 4.78 |
| standard deviation | 0.68 |
| range | 2.3 to 7.7 |
| "would want a second date" | 114 of 600 verdicts (19%) |

Rankings (corrected for each rater's harshness and each person's broad appeal):

- All 25 raters rank all 24 others.
- Nobody dominates: no person is ranked first by more than 2 of 25 raters; the most popular first choice is picked by 2.
- Mean rank per person runs from 10.6 to 14.5 (the middle would be 12.5).
- Of 600 directed pairs: 332 "mutual" (the two sides scored each other about the same), 134 "you like them more", 134 "they like you more".

### Do similar people match, or opposites?

Rank correlation with the adjusted date score over 552 directed pairs:

| Baseline | Spearman |
|---|---|
| shared values, lifestyle and interests | **+0.10** |
| complementary pace, social style and tempo (only counted where values overlap) | **+0.12** |

Both are weak and neither idea wins. With 25 people this is close to noise, and the site reports it that way without
tuning anything to make either hypothesis look better.

## Consistency checks (`python -m scripts.diagnostics`)

| Check | Result | Reading |
|---|---|---|
| Same verdict asked twice | r = **0.78**, n = 60 verdicts; scores moved 0.36 points on average | reasonably repeatable |
| Speaker order swapped (10 dates replayed with the other agent first) | mean shift **+0.02** | no first-speaker advantage on average |
| Replayed date versus original, composite score | r = 0.57, n = 10 | a regenerated date is a new conversation, so this mixes order effect and ordinary variation |
| Richer profile, higher score | r = **+0.38**, n = 25 | profiles with more text receive higher scores; reported and not adjusted for |

The order-swap sample is small; treat it as weak evidence.

## Live run (a judge pasting a person)

One person pasted with "rank against the demo" on: scrape 30 s, read 30 s, 25 dates about 4 minutes, rank 8 s; **5 min 28 s total,
$0.19, 350 Gemini calls**, all 25 dates done. The 25 demo members' own rankings were unchanged, and their view of the new person
was scored from date scores only (labelled in the UI). One run; not a distribution.

## What these results do and do not show

They show that the harness is consistent enough to read (verdicts repeat, order does not matter, nobody dominates), that its
numbers are produced by an auditable chain (every claim to an observation to a source line; every quote to a transcript line),
and that cost stays small. They do not show that a high rank means two people would get along, and they do not show that
similar or opposite people match better. Correctness cannot be measured from two public profiles.
