"""LLM access: cache by input hash, token bucket per provider, backoff on 429, provider fallback
(SPEC §10 runner mechanics). Provider adapters implement `LLM`; none are wired to a real API yet."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Protocol


class RateLimited(Exception):
    pass


class BudgetExceeded(Exception):
    """A provider hit its configured daily call cap. Never retried: stop before a paid tier is touched."""


class LLM(Protocol):
    name: str

    async def complete(self, system: str, user: str, temperature: float,
                       json_mode: bool = False) -> str: ...


class Cache(Protocol):
    async def get(self, key: str): ...
    async def set(self, key: str, value: str) -> None: ...


class MemoryCache:
    def __init__(self):
        self.d: dict[str, str] = {}

    async def get(self, key):
        return self.d.get(key)

    async def set(self, key, value):
        self.d[key] = value


def cache_key(prompt_version: str, system: str, user: str, temperature: float, sample: int = 0) -> str:
    """Includes `sample` so VERDICT_SAMPLES draws are distinct cache entries."""
    blob = json.dumps([prompt_version, system, user, round(temperature, 3), sample], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


class TokenBucket:
    def __init__(self, per_minute: float, burst: float | None = None):
        self.rate = per_minute / 60.0
        self.cap = burst if burst is not None else max(1.0, per_minute / 6)  # small burst
        self.tokens = self.cap
        self.t = time.monotonic()
        self.lock = asyncio.Lock()

    async def take(self, n: float = 1.0):
        n = min(n, self.cap)  # a single oversized request still proceeds once the bucket is full
        async with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.cap, self.tokens + (now - self.t) * self.rate)
                self.t = now
                if self.tokens >= n:
                    self.tokens -= n
                    return
                await asyncio.sleep((n - self.tokens) / self.rate)


class Gateway:
    def __init__(self, providers: list[LLM], cache: Cache | None = None,
                 per_minute: dict[str, float] | None = None, max_retries: int = 4,
                 base_delay: float = 1.0, daily_caps: dict[str, int] | None = None,
                 prices: dict[str, tuple[float, float]] | None = None, budget_usd: float | None = None,
                 routes: dict[str, list[LLM]] | None = None,
                 tpm: dict[str, float] | None = None):
        self.providers = providers
        # named provider chains, e.g. "turns" -> free Groq models first, Gemini as fallback
        self.routes = routes or {}
        self.tpm_buckets = {n: TokenBucket(v, burst=v) for n, v in (tpm or {}).items()}
        self.prices = prices or {}  # provider name -> (USD per 1M input, USD per 1M output); absent = free
        self.budget_usd = budget_usd
        self.spend_usd = 0.0
        self.daily_caps = daily_caps or {}
        self.usage = {p.name: {"calls": 0, "est_tokens": 0} for p in providers}  # estimate: chars / 4
        self.cache = cache or MemoryCache()
        self.buckets = {p.name: TokenBucket((per_minute or {}).get(p.name, 600)) for p in providers}
        self.max_retries, self.base_delay = max_retries, base_delay
        self.calls = {p.name: 0 for p in providers}

    async def complete(self, *, prompt_version: str, system: str, user: str, temperature: float,
                       sample: int = 0, json_mode: bool = False, route: str | None = None,
                       route_key: str | int | None = None,
                       images: list[bytes] | None = None) -> tuple[str, str]:
        """Returns (text, provider_name or 'cache'). `route` picks a provider chain; `route_key`
        rotates the starting provider within the chain's leading free providers (stable per key,
        so both sides of one date use the same model)."""
        img_sig = hashlib.sha256(b"".join(images)).hexdigest() if images else ""
        key = cache_key(prompt_version, system, user + img_sig, temperature, sample)
        hit = await self.cache.get(key)
        if hit is not None:
            return hit, "cache"
        last: Exception | None = None
        # primary first; fall back down the chain only after retries on a provider are exhausted
        chain = list(self.routes.get(route, self.providers)) if route else list(self.providers)
        if route_key is not None:
            lead = []
            for p in chain:
                if p.name in self.prices:
                    break
                lead.append(p)
            if len(lead) > 1:
                k = int(hashlib.sha256(str(route_key).encode()).hexdigest(), 16) % len(lead)
                chain = lead[k:] + lead[:k] + chain[len(lead):]
        for p in chain:
            for attempt in range(self.max_retries):
                cap = self.daily_caps.get(p.name)
                paid = p.name in self.prices
                if (cap is not None and self.calls[p.name] >= cap) or (
                        paid and self.budget_usd is not None and self.spend_usd >= self.budget_usd):
                    last = BudgetExceeded(p.name)
                    break  # this provider is spent: try the next (free) one
                await self.buckets[p.name].take()
                if p.name in self.tpm_buckets:  # estimate prompt + a modest reply
                    await self.tpm_buckets[p.name].take((len(system) + len(user)) // 4 + 300)
                try:
                    self.calls[p.name] += 1
                    text = await (p.complete(system, user, temperature, json_mode, images=images)
                                  if images else p.complete(system, user, temperature, json_mode))
                    self.usage[p.name]["calls"] += 1
                    tin = getattr(text, "in_tok", None) or (len(system) + len(user)) // 4
                    tout = getattr(text, "out_tok", None) or len(text) // 4
                    self.usage[p.name]["est_tokens"] += tin + tout
                    if paid:
                        pin, pout = self.prices[p.name]
                        self.spend_usd += (tin * pin + tout * pout) / 1e6
                    await self.cache.set(key, text)
                    return text, p.name
                except RateLimited as e:
                    last = e
                    await asyncio.sleep(self.base_delay * 2 ** attempt)
                except Exception as e:  # provider error: next provider
                    last = e
                    break
        if isinstance(last, BudgetExceeded):
            raise last
        raise RuntimeError(f"all providers failed: {last!r}")


def build_default_gateway(cache: "Cache | None" = None) -> Gateway:
    """Routing policy: free Groq models carry date turns (the bulk of calls); Gemini Flash-Lite
    carries verdicts, extraction, vision and ranking, and is the fallback for turns. Groq is the
    fallback for Gemini jobs, so a spent dollar budget degrades to free instead of failing."""
    from app.config import settings as s
    from app.llm.providers import Gemini, Groq
    g120, g20, qw = Groq("openai/gpt-oss-120b"), Groq("openai/gpt-oss-20b"), Groq("qwen/qwen3.8-27b")
    gem = Gemini()
    return Gateway(
        [gem, g120, g20, qw], cache=cache, prices=s.prices, budget_usd=s.llm_budget_usd,
        daily_caps=s.daily_caps,
        per_minute={p.name: 20 for p in (g120, g20, qw)},
        tpm={p.name: 7000 for p in (g120, g20, qw)},  # Groq free: 8K TPM, keep a margin
        routes={"turns": [g120, g20, qw, gem], "verdict": [gem, g120, g20, qw],
                "live": [gem, g120, g20, qw]},  # live judges wait on the page: Gemini first (fast)
    )


class DbCache:
    """llm_cache table behind an in-memory layer. Reruns after a crash or a prompt-neutral restart
    cost nothing. Responses are plain strings stored as JSON."""

    def __init__(self, sessionmaker):
        self.sm, self.mem = sessionmaker, {}

    async def get(self, key):
        if key in self.mem:
            return self.mem[key]
        from app.db.models import LlmCache
        try:
            async with self.sm() as db:
                row = await db.get(LlmCache, key)
        except Exception:
            return None  # cache is best-effort
        if row is not None:
            self.mem[key] = row.response
            return row.response
        return None

    async def set(self, key, value):
        self.mem[key] = str(value)
        from sqlalchemy.dialects.postgresql import insert
        from app.db.models import LlmCache
        try:
            async with self.sm() as db:
                await db.execute(insert(LlmCache).values(key=key, response=str(value))
                                 .on_conflict_do_nothing(index_elements=["key"]))
                await db.commit()
        except Exception:
            pass
