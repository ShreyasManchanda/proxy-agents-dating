import { ArrowRight, Plus, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Json } from "../api";
import { Notice } from "../components/ui";

type Row = { linkedin: string; instagram: string };
const blank = (): Row => ({ linkedin: "", instagram: "" });

export default function Landing() {
  const nav = useNavigate();
  const [cfg, setCfg] = useState<Json | null>(null);
  const [demo, setDemo] = useState<Json | null>(null);
  const [rows, setRows] = useState<Row[]>([blank()]);
  const [joinDemo, setJoinDemo] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.config().then((c) => {
      setCfg(c);
      if (c.demo_token) api.pool(c.demo_token).then(setDemo).catch(() => {});
    }).catch(() => setErr("Could not reach the server. Try again in a moment."));
  }, []);

  const max = cfg?.live_pool_max ?? 5;
  const filled = rows.filter((r) => r.linkedin.trim() || r.instagram.trim());
  const needed = joinDemo ? 1 : 2;
  const pasteOff = cfg && !cfg.paste_enabled;
  const noRuns = cfg && cfg.live_runs_left <= 0;

  const setRow = (i: number, k: keyof Row, v: string) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (filled.length < needed) return setErr(joinDemo ? "Add at least one person." : "Untick the demo option only if you are adding at least two people.");
    if (filled.some((r) => !r.linkedin.trim() || !r.instagram.trim())) return setErr("Each person needs both a LinkedIn and an Instagram link.");
    setBusy(true);
    try {
      const out = await api.createPool(filled, joinDemo);
      if (out.redirect) nav(`/p/${out.redirect.token}/person/${out.redirect.person_id}`);  // already in the demo
      else nav(`/p/${out.token}`);
    } catch (x) {
      setErr((x as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="hero">
      <section aria-labelledby="h">
        <h1 id="h">Your agent goes on the dates.</h1>
        <p className="lede">
          Paste a LinkedIn and a public Instagram. An agent reads them, builds a profile you can check against its evidence,
          then dates every other agent. The ranking comes from the dates.
        </p>

        <form className="pastebox" onSubmit={submit} noValidate>
          {rows.map((r, i) => (
            <div className="pair" key={i}>
              <label className="field">
                <span className={i ? "sr" : ""}>LinkedIn profile</span>
                <input type="url" inputMode="url" placeholder="linkedin.com/in/name" value={r.linkedin} onChange={(e) => setRow(i, "linkedin", e.target.value)} autoComplete="off" />
              </label>
              <label className="field">
                <span className={i ? "sr" : ""}>Instagram profile</span>
                <input type="url" inputMode="url" placeholder="instagram.com/handle" value={r.instagram} onChange={(e) => setRow(i, "instagram", e.target.value)} autoComplete="off" />
              </label>
              <button type="button" className="x" aria-label={`Remove person ${i + 1}`} onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs))}><X size={16} /></button>
            </div>
          ))}
          <div className="row-actions">
            <button type="button" className="btn ghost sm" disabled={rows.length >= max} onClick={() => setRows((rs) => [...rs, blank()])}>
              <Plus size={16} aria-hidden /> Add person <span className="muted xs">({rows.length}/{max})</span>
            </button>
            <label className="small" style={{ display: "flex", gap: "0.5rem", alignItems: "center", minHeight: 44 }}>
              <input type="checkbox" checked={joinDemo} onChange={(e) => setJoinDemo(e.target.checked)} />
              Rank against the 25-person demo too (recommended)
            </label>
          </div>
          {err && <Notice kind="bad">{err}</Notice>}
          {pasteOff && <Notice kind="warn">New runs are switched off for now. The demo is still open.</Notice>}
          {noRuns && !pasteOff && <Notice kind="warn">Today's live runs are used up. The demo is still open; try a new run tomorrow.</Notice>}
          <p className="small muted" style={{ maxWidth: "60ch" }}>
            {joinDemo
              ? `Each person dates all 25 in the demo, and anyone you add dates each other. Live runs are limited to ${max} people.`
              : `Only the people you add date each other, so add at least two. Live runs are limited to ${max} people.`}
            {" "}One person takes about five minutes with the demo, a couple without.
          </p>
          <div className="row-actions">
            <button className="btn" type="submit" disabled={busy || !!pasteOff || !!noRuns}>
              {busy ? "Starting…" : "Start the dates"} <ArrowRight size={18} aria-hidden />
            </button>
            {cfg && !pasteOff && <span className="small muted">{cfg.live_runs_left} live runs left today</span>}
          </div>
        </form>
      </section>

      <aside style={{ display: "grid", gap: "1.25rem" }} aria-label="Demo and data notes">
        <div className="demo-box">
          <h3>The 25-person demo</h3>
          <p className="small muted">Already run: every pair has met. Read any profile, any date, and the rankings. It works with the live services switched off.</p>
          {demo && (
            <div className="stats">
              <div><b>{demo.people?.length ?? 0}</b><span className="small muted">people</span></div>
              <div><b>{demo.dates_done ?? 0}</b><span className="small muted">dates</span></div>
            </div>
          )}
          {demo?.synthetic && <Notice kind="warn">This demo currently holds made-up test people, not the real 25.</Notice>}
          {cfg?.demo_token
            ? <Link className="btn" to={`/p/${cfg.demo_token}`}>Open the demo <ArrowRight size={18} aria-hidden /></Link>
            : <button className="btn" disabled>Demo not published yet</button>}
        </div>
        <div>
          <h3 style={{ marginBottom: "0.6rem" }}>What the agents see</h3>
          <ul className="sees">
            <li>Only the public LinkedIn and Instagram you paste. Nothing else.</li>
            <li>What someone states in their own words, like wanting kids, can matter. Faith, orientation, health and politics are never guessed from photos, follows or style.</li>
            <li>Pasted people are private to your link, and you can delete them.</li>
            <li>We rank compatibility, not eligibility.</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
