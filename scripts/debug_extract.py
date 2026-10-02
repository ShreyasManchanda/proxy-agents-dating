import asyncio
import sys

from app.extract.pipeline import ig_block, li_block, load_prompt
from app.llm.gateway import build_default_gateway
from app.normalize.canonical import normalize_person
from fixtures.synthetic import build


async def main(i):
    p = build(i)
    c = normalize_person(p["ig"], p["li"], p["li_posts"])
    gw = build_default_gateway()
    t1, r1, o1 = ig_block(c["instagram"])
    t2, r2, o2 = li_block(c["linkedin"])
    own = {**o1, **o2}
    block = "\n".join(f"[{r}] {t}" for r, t in own.items())
    sys_, v = load_prompt("stated")
    text, who = await gw.complete(prompt_version=v + "dbg", system=sys_, user=f"<data>\n{block}\n</data>",
                                  temperature=0.3, json_mode=True)
    print("STATED RAW (", who, "):", text[:600])
    sys_, v = load_prompt("synthesis")
    text, who = await gw.complete(
        prompt_version=v + "dbg", system=sys_, user="<data>\nobservations:\nobs_1 [ig/hobby] Dives on reef surveys\n"
        "obs_2 [li/work] Research Fellow at CSIR NIO\n\nstated_signals: []\n</data>", temperature=0.3, json_mode=True)
    print("SYNTH RAW (", who, "):", text[:1200])

asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 6))
