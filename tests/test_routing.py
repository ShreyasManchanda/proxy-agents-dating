import time

import pytest

from app.llm.gateway import Gateway, TokenBucket


class P:
    def __init__(self, name):
        self.name = name

    async def complete(self, *a, **k):
        return self.name


async def test_routes_prefer_free_and_rotate_by_key():
    g1, g2, g3, gem = P("g1"), P("g2"), P("g3"), P("gem")
    g = Gateway([gem, g1, g2, g3], max_retries=1, base_delay=0, prices={"gem": (1.0, 1.0)},
                routes={"turns": [g1, g2, g3, gem]})
    seen = set()
    for k in range(30):
        _, who = await g.complete(prompt_version="v", system="s", user=f"u{k}", temperature=0.3,
                                  route="turns", route_key=k)
        seen.add(who)
    assert seen == {"g1", "g2", "g3"} and g.calls["gem"] == 0  # free chain used, Gemini untouched
    a = await g.complete(prompt_version="v", system="s", user="x", temperature=0.3, route="turns", route_key="7-9")
    b = await g.complete(prompt_version="v", system="s", user="y", temperature=0.3, route="turns", route_key="7-9")
    assert a[1] == b[1]  # same date -> same model for both speakers


async def test_free_chain_exhausted_falls_to_paid():
    g1, gem = P("g1"), P("gem")
    g = Gateway([gem, g1], max_retries=1, base_delay=0, prices={"gem": (1.0, 1.0)},
                daily_caps={"g1": 1}, routes={"turns": [g1, gem]})
    got = [(await g.complete(prompt_version="v", system="s", user=f"u{i}", temperature=0.3,
                             route="turns"))[1] for i in range(3)]
    assert got == ["g1", "gem", "gem"]


async def test_tpm_bucket_delays_instead_of_429():
    tb = TokenBucket(6000, burst=1000)  # 100 tokens/sec
    await tb.take(1000)
    t = time.monotonic()
    await tb.take(100)
    assert 0.5 < time.monotonic() - t < 2.0
