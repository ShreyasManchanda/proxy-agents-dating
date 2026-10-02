"""Run extraction on one synthetic person with the real LLMs and print the result.
Run: python -m scripts.try_extract [index]"""
import asyncio
import json
import sys

from app.extract.pipeline import extract_person
from app.llm.gateway import build_default_gateway
from app.normalize.canonical import normalize_person
from fixtures.synthetic import build


async def main(i: int):
    p = build(i)
    canon = normalize_person(p["ig"], p["li"], p["li_posts"])
    gw = build_default_gateway()
    out = await extract_person(gw, canon, None, p["name"])
    prof = out["profile"]
    print(f"observations kept={len(out['observations'])} dropped={out['dropped_observations']}")
    for o in out["observations"][:6]:
        print(" ", o["id"], o["source"], o["kind"], o["ref"], "|", o["text"][:90])
    print("stated:", [(s["topic"], s["quote"]) for s in prof["stated_signals"]])
    print("needs:", [c["claim"] for c in prof["needs"]])
    print("hobbies:", [c["claim"] for c in prof["hobbies"]])
    print("contradictions:", [c["claim"] for c in prof["contradictions"]])
    print("hooks:", prof["conversation_hooks"])
    print("tags:", prof["tags"], "dials:", prof["dials"], "conf:", prof["overall_confidence"])
    print("\n--- PERSONA CARD ---\n" + out["persona_card"])
    print("\nusage:", json.dumps(gw.usage), "spend_usd=%.4f" % gw.spend_usd)


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 0))
