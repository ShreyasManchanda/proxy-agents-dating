"""Smoke test the real adapters, including Gemini vision. Run: python -m scripts.smoke_llm"""
import asyncio
import io

from PIL import Image, ImageDraw

from app.llm.gateway import RateLimited
from app.llm.providers import Gemini, Groq


def test_image() -> bytes:
    im = Image.new("RGB", (512, 384), (40, 120, 60))
    d = ImageDraw.Draw(im)
    d.rectangle((60, 200, 260, 330), fill=(150, 90, 40))
    d.ellipse((300, 60, 420, 180), fill=(250, 220, 40))
    d.text((70, 150), "SUNDAY HIKE CLUB", fill=(255, 255, 255))
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


async def try_call(label, coro_fn, tries=4):
    for i in range(tries):
        try:
            print(f"{label}: {(await coro_fn())[:300]!r}")
            return
        except RateLimited:
            print(f"{label}: 429, waiting 30s (try {i + 1})")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"{label}: ERR {e!r}")
            return


async def main():
    img = test_image()
    vis = ("Describe only what is visible.", "Return JSON {activity, setting, objects, text_in_image}.")
    for model in ("gemini-3.5-flash-lite", "gemma-4-31b-it"):
        g = Gemini(model)
        await try_call(f"{model} vision", lambda g=g: g.complete(*vis, 0.3, True, images=[img]))
        await try_call(f"{model} text", lambda g=g: g.complete("Be terse.", "Say hi in 3 words.", 0.3))
    for m in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
        await try_call(m, lambda m=m: Groq(m).complete("Be terse.", "Say hi in 3 words.", 0.3))


if __name__ == "__main__":
    asyncio.run(main())
