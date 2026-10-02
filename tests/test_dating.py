import json

import pytest

from app.config import Settings
from app.dating.runner import Person, first_speaker, phase_for_turn, run_date, scenario_for
from app.llm.gateway import Gateway, RateLimited, cache_key

A = Person(1, "Asha", "Asha runs a design studio and climbs on weekends.")
B = Person(2, "Ben", "Ben is a nurse who cooks for friends every Sunday.")
CFG = Settings()


SENTENCES = [
    "Mornings at the climbing gym beat any coffee for me.", "I batch-cook lentils every Sunday evening.",
    "Our studio just shipped a typeface for a bakery.", "Night shifts taught me to nap anywhere.",
    "Monsoon trips to the hills are my reset button.", "I keep a paper planner despite everyone laughing.",
    "Sketching strangers on trains is a bad habit.", "My sister and I swap playlists every Friday.",
    "Pottery class flooded my kitchen last week.", "Tamil films are my comfort viewing.",
    "Board game nights get surprisingly competitive.", "Trekking without a phone changed how I plan.",
    "Rooftop gardens are underrated for quiet evenings.",
]


class Fake:
    name = "fake"

    def __init__(self, bad_first=False):
        self.n = 0
        self.systems = []
        self.bad_first = bad_first

    async def complete(self, system, user, temperature, json_mode=False):
        self.n += 1
        self.systems.append(system)
        if "private verdict" in system:
            return json.dumps({"scores": {d: 7 for d in ("candor_ease", "mutual_enjoyment", "attentiveness",
                                                         "positivity", "coordination", "perceived_similarity")},
                               "second_date": True, "reason": "Warm and specific.", "quote": "worth a try"})
        if self.bad_first and self.n == 1:
            return "That's so interesting, tell me more about everything you do!"
        topic = SENTENCES[self.n % len(SENTENCES)]
        return f"{topic} Honestly it is worth a try."


def gw(p, **kw):
    return Gateway([p], max_retries=3, base_delay=0, **kw)


def test_deterministic_order_scenario_and_phases():
    assert scenario_for(1, 2) == scenario_for(2, 1) and first_speaker(1, 2) == first_speaker(2, 1)
    assert [phase_for_turn(i, (3, 4, 3)) for i in range(10)] == ["intro"] * 3 + ["disclosure"] * 4 + ["scenario"] * 3


async def test_full_date_alternates_and_never_shows_partner_card():
    p = Fake()
    events = []

    async def emit(kind, data):
        events.append(kind)
    res = await run_date(gw(p), A, B, emit=emit, cfg=CFG)
    assert len(res.transcript) == 10
    speakers = [t["speaker"] for t in res.transcript]
    assert all(speakers[i] != speakers[i + 1] for i in range(9)) and speakers[0] == first_speaker(1, 2)
    turn_systems = [s for s in p.systems if "PHASE:" in s]
    for s in turn_systems:  # exactly one persona per prompt
        assert ("design studio" in s) != ("nurse" in s)
    assert events[0] == "date_started" and events[-1] == "date_done" and events.count("turn") == 10
    assert res.verdicts[1] and res.verdicts[2] and len(res.verdicts[1]) == CFG.verdict_samples


async def test_resume_continues_from_saved_turn():
    saved = []

    async def save(t):
        saved.append(len(t))
    p = Fake()
    first = await run_date(gw(p), A, B, save=save, cfg=CFG)
    partial = first.transcript[:4]
    p2 = Fake()
    again = await run_date(gw(p2), A, B, transcript=partial, cfg=CFG)
    assert saved == list(range(1, 11))
    assert len(again.transcript) == 10 and again.transcript[:4] == partial
    assert sum("PHASE:" in s for s in p2.systems) == 6  # only the missing turns were generated


async def test_guard_regenerates_once_and_flags():
    p = Fake(bad_first=True)
    res = await run_date(gw(p), A, B, cfg=CFG, plan=(1, 0, 0), samples=1)
    assert "interesting" not in res.transcript[0]["text"] and "flags" not in res.transcript[0]


async def test_verdict_with_fabricated_quote_is_rejected():
    class Liar(Fake):
        async def complete(self, system, user, temperature, json_mode=False):
            out = await super().complete(system, user, temperature, json_mode)
            return out.replace("worth a try", "never said this") if "private verdict" in system else out
    res = await run_date(gw(Liar()), A, B, cfg=CFG, plan=(2, 0, 0), samples=1)
    assert res.verdicts[1] == [] and any(f.startswith("verdict_failed") for f in res.flags)


async def test_cache_hit_skips_provider():
    p = Fake()
    g = gw(p)
    kw = dict(prompt_version="v", system="s", user="u", temperature=0.3)
    t1, who1 = await g.complete(**kw)
    t2, who2 = await g.complete(**kw)
    assert (t1, who1, who2) == (t2, "fake", "cache") and p.n == 1
    assert cache_key("v", "s", "u", 0.3, 0) != cache_key("v", "s", "u", 0.3, 1)


async def test_backoff_then_fallback():
    class Limited:
        name = "groq"

        async def complete(self, *a, **k):
            raise RateLimited()

    class Ok:
        name = "gemini"

        async def complete(self, *a, **k):
            return "ok"
    g = Gateway([Limited(), Ok()], max_retries=2, base_delay=0)
    text, who = await g.complete(prompt_version="v", system="s", user="u", temperature=0.3)
    assert (text, who) == ("ok", "gemini") and g.calls["groq"] == 2


async def test_daily_cap_stops_calls_and_falls_back():
    from app.llm.gateway import BudgetExceeded

    class P:
        def __init__(self, name):
            self.name, self.n = name, 0

        async def complete(self, *a, **k):
            self.n += 1
            return "x"
    a, b = P("a"), P("b")
    g = Gateway([a, b], max_retries=1, base_delay=0, daily_caps={"a": 2})
    for i in range(4):
        await g.complete(prompt_version="v", system="s", user=f"u{i}", temperature=0.3)
    assert (a.n, b.n) == (2, 2) and g.usage["a"]["calls"] == 2
    only = Gateway([P("a")], max_retries=1, base_delay=0, daily_caps={"a": 0})
    with pytest.raises(BudgetExceeded):
        await only.complete(prompt_version="v", system="s", user="u", temperature=0.3)


async def test_dollar_budget_stops_paid_provider_but_free_continues():
    from app.llm.providers import _with_usage

    class Paid:
        name = "paid"

        async def complete(self, *a, **k):
            return _with_usage("x", 1_000_000, 0)  # exactly $1 at (1.0, 0)

    class Free:
        name = "free"

        async def complete(self, *a, **k):
            return "y"
    g = Gateway([Paid(), Free()], max_retries=1, base_delay=0, prices={"paid": (1.0, 0.0)}, budget_usd=2.0)
    who = [(await g.complete(prompt_version="v", system="s", user=f"u{i}", temperature=0.3))[1] for i in range(4)]
    assert who == ["paid", "paid", "free", "free"] and g.spend_usd == pytest.approx(2.0)


def test_trim_words_cuts_at_sentence_boundary():
    from app.dating.runner import _trim_words
    t = "I like rivers. I also like long walks, and I never know when to stop talking about them so I keep going"
    out = _trim_words(t, 12)
    assert out.endswith(".") and len(out.split()) <= 12
    assert _trim_words("one two three four five six seven eight nine ten", 5).endswith(".")
