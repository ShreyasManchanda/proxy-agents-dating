"""Real provider adapters for the Gateway (SPEC §2, §16.1). Model names come from config."""
from __future__ import annotations

import base64

import httpx

from app.config import settings
from app.llm.gateway import RateLimited

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class Text(str):
    """Completion text carrying real token counts from the provider, when it reports them."""
    in_tok: int | None = None
    out_tok: int | None = None


def _with_usage(text: str, i, o) -> Text:
    t = Text(text)
    t.in_tok, t.out_tok = i, o
    return t


def _check(r: httpx.Response, who: str) -> None:
    if r.status_code == 429:
        raise RateLimited(who)
    if r.status_code >= 400:
        raise RuntimeError(f"{who} {r.status_code}: {r.text[:200]}")


class Gemini:
    def __init__(self, model: str | None = None, name: str | None = None):
        self.model = model or settings.gemini_model
        self.name = name or f"gemini:{self.model}"

    async def complete(self, system: str, user: str, temperature: float, json_mode: bool = False,
                       images: list[bytes] | None = None) -> str:
        parts = [{"text": user}] + [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode()}}
            for b in images or []]
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": temperature,
                                     **({"responseMimeType": "application/json"} if json_mode else {})}}
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(GEMINI_URL.format(model=self.model), json=body,
                             headers={"x-goog-api-key": settings.gemini_api_key})
        _check(r, self.name)
        cand = r.json()["candidates"][0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        if not text:
            raise RuntimeError(f"{self.name} empty response (finish={cand.get('finishReason')})")
        u = r.json().get("usageMetadata") or {}
        # output includes thinking tokens, which Gemini bills as output
        out = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
        return _with_usage(text, u.get("promptTokenCount"), out or None)


class Groq:
    def __init__(self, model: str | None = None):
        self.model = model or settings.groq_model
        self.name = f"groq:{self.model}"

    async def complete(self, system: str, user: str, temperature: float, json_mode: bool = False,
                       images: list[bytes] | None = None) -> str:
        if images:  # never silently drop images: a text-only answer about photos would be invented
            raise RuntimeError(f"{self.name} has no vision support")
        body = {"model": self.model, "temperature": temperature, "max_tokens": 1500,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if "gpt-oss" in self.model:
            body["reasoning_effort"] = "low"  # otherwise hidden reasoning can eat the whole budget
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {settings.groq_api_key}"})
        _check(r, self.name)
        text = (r.json()["choices"][0]["message"].get("content") or "").strip()
        if not text:
            raise RuntimeError(f"{self.name} empty response")
        u = r.json().get("usage") or {}
        return _with_usage(text, u.get("prompt_tokens"), u.get("completion_tokens"))
