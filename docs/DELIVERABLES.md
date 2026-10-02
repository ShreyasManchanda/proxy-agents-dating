# Deliverables

## 200-character explanation (183 characters)
> Paste a LinkedIn + public Instagram per person; an AI agent reads them, builds a profile, then dates every other agent on their behalf. Rankings come from the dates, not the profiles.

## 500-character tech section (428 characters)
> Apify actors via API, no cookies or login: apify/instagram-scraper (profile + latest 12 posts/reels, music, tags), harvestapi/linkedin-profile-scraper (experience, education, skills) and harvestapi/linkedin-profile-posts. Raw JSON cached in Postgres, images downloaded at ingest, Gemini vision reads photos. Python/FastAPI async pipeline: observers -> evidence-cited synthesis -> agent-vs-agent dates -> rank-normalized scoring.

## Video script (3:00 max): profile pages first, then rankings, with the agents actually dating
Record at 1280x800, light theme, browser zoom 110%. Use the 25-person demo for everything except the pasted-person beat.

| Time | Show | Say |
|---|---|---|
| 0:00-0:15 | Landing page, then paste two links | "Every person gets an agent. It reads only their public LinkedIn and Instagram, then dates every other agent for them." |
| 0:15-0:50 | Demo roster, open one profile, expand a claim to its evidence, point at the confidence badge and a "not enough signal" line | "This profile is not a guess. Every claim opens to the post or job behind it, with a confidence. Where there is little to read, it says so." |
| 0:50-1:45 | Open a date. Scroll the transcript, phase labels, then the two verdicts with the highlighted quote | "Two agents, one model call per turn, neither sees the other's profile. Each writes a blind verdict, and its quote has to be a real line from the date." |
| 1:45-2:15 | Dating grid, click a low-scoring square, show the agents disagreeing | "Every pair has met. Here the two agents disagreed: one wanted a second date, the other did not, and said why." |
| 2:15-2:50 | Rankings: switch person, move the own-vs-mutual slider, open About the results (similar vs opposite, consistency checks) | "Rankings come from the dates, corrected for harsh and generous scorers. We tested whether similar or opposite people match better and report what the data says." |
| 2:50-3:00 | Landing page with the URL | "Agents only see LinkedIn and Instagram, so we rank compatibility, not eligibility." |

Beat to record separately and cut in: paste two real links, watch scraping to ranking (about 2 minutes live).
Every shipped feature must work or be removed: paste, join-the-demo, slider, About panel, delete.
