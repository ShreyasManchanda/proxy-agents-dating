import { ArrowRight, CheckCircle, CircleNotch, Trash } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, initials, type Json } from "../api";
import { Notice, Skeleton, confidenceWord, fmt } from "../components/ui";

const PHASES = [
  { key: "reading", label: "Reading profiles" },
  { key: "dating", label: "Dating" },
  { key: "ranking", label: "Ranking" },
  { key: "done", label: "Done" },
];
const TABS = [["people", "People"], ["grid", "Dating grid"], ["rankings", "Rankings"], ["about", "About the results"]] as const;

function usePool(token: string) {
  const [pool, setPool] = useState<Json | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.pool(token).then((p) => { setPool(p); setError(null); }).catch((e) => setError(e.message)), [token]);
  useEffect(() => { load(); }, [load]);
  const running = pool && !["done", "failed"].includes(pool.phase);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [running, load]);
  return { pool, error, reload: load };
}

export default function Pool() {
  const { token = "" } = useParams();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || "people";
  const { pool, error, reload } = usePool(token);

  if (error && !pool) return <Notice kind="bad">{error}</Notice>;
  if (!pool) return <div style={{ display: "grid", gap: "1rem" }}><Skeleton h={36} w="40%" /><Skeleton h={48} /><Skeleton h={240} /></div>;

  const phaseIdx = Math.max(0, PHASES.findIndex((p) => p.key === pool.phase));
  const finished = pool.phase === "done" || pool.frozen;
  const pct = pool.dates_total ? Math.round((pool.dates_done / pool.dates_total) * 100) : 0;

  return (
    <>
      <div className="pool-head">
        <div>
          <h1 style={{ fontSize: "var(--t-xl)" }}>{pool.name}</h1>
          <p className="small muted" style={{ marginTop: "0.3rem" }}>
            {pool.people.length} people · {pool.dates_done} of {pool.dates_total} dates done
            {pool.dates_failed ? ` · ${pool.dates_failed} need a retry` : ""}
          </p>
        </div>
      </div>

      {pool.synthetic && <div style={{ marginBottom: "1rem" }}><Notice kind="warn">These are made-up test people used to build the site, not real profiles.</Notice></div>}
      {pool.phase === "failed" && <div style={{ marginBottom: "1rem" }}><Notice kind="bad">{pool.error || "This run could not finish."}</Notice></div>}

      {!finished && pool.phase !== "failed" && (
        <>
          <ol className="steps" aria-label="Progress">
            {PHASES.map((p, i) => (
              <li key={p.key} className={i < phaseIdx ? "done" : i === phaseIdx ? "now" : ""} aria-current={i === phaseIdx ? "step" : undefined}>
                {i < phaseIdx ? <CheckCircle size={16} weight="fill" aria-hidden /> : i === phaseIdx ? <CircleNotch size={16} className="spin" aria-hidden /> : null}
                <span className="t">{p.label}</span>
              </li>
            ))}
          </ol>
          {pool.phase === "dating" && <div className="progressbar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} style={{ marginBottom: "1.5rem" }}><i style={{ width: `${pct}%` }} /></div>}
        </>
      )}

      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setSp({ tab: k })}>{label}</button>
        ))}
      </div>

      {tab === "people" && <People token={token} pool={pool} />}
      {tab === "grid" && <Grid token={token} pool={pool} />}
      {tab === "rankings" && <Rankings token={token} pool={pool} />}
      {tab === "about" && <About token={token} pool={pool} onChange={reload} />}
    </>
  );
}

function People({ token, pool }: { token: string; pool: Json }) {
  return (
    <div className="roster" role="list">
      {pool.people.map((p: Json) => {
        const c = confidenceWord(p.confidence);
        const ready = p.status === "ready";
        return (
          <Link role="listitem" key={p.id} className="person-row" to={ready ? `/p/${token}/person/${p.id}` : "#"} onClick={(e) => !ready && e.preventDefault()} aria-disabled={!ready}>
            <span className="avatar" aria-hidden>{initials(p.name)}</span>
            <div style={{ minWidth: 0 }}>
              <div className="nm">{p.name || "Reading…"}</div>
              <div className="xs muted">{p.location || (ready ? "" : statusText(p.status))}</div>
            </div>
            <div className="sub">{p.note && p.status !== "ready" ? p.note : p.headline}</div>
            {ready
              ? <span className={`chip ${c.cls}`}>{c.word}</span>
              : <span className={`chip ${p.status === "failed" ? "bad" : ""}`}>{statusText(p.status)}</span>}
          </Link>
        );
      })}
    </div>
  );
}
const statusText = (s: string) => ({ pending: "Queued", scraping: "Scraping", reading: "Reading", ready: "Ready", failed: "Failed" } as Record<string, string>)[s] || s;

function Grid({ token, pool }: { token: string; pool: Json }) {
  const [dates, setDates] = useState<Json[]>([]);
  useEffect(() => {
    const load = () => api.dates(token).then(setDates).catch(() => {});
    load();
    if (["done", "failed"].includes(pool.phase) || pool.frozen) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [token, pool.phase, pool.frozen]);
  const cell = useMemo(() => {
    const m = new Map<string, Json>();
    dates.forEach((d) => { m.set(`${d.a}-${d.b}`, d); m.set(`${d.b}-${d.a}`, d); });
    return m;
  }, [dates]);
  const ready = pool.people.filter((p: Json) => p.status === "ready");
  if (ready.length < 2) return <div className="empty"><h3>Nobody to date yet</h3><p className="small">The grid appears once at least two profiles are ready.</p></div>;
  return (
    <>
      <p className="small muted" style={{ marginBottom: "0.9rem" }}>Each square is one date. Darker means the two agents scored it higher. Open any square to read the transcript.</p>
      <div className="matrix-wrap">
        <table className="matrix">
          <thead><tr><th scope="col" /> {ready.map((p: Json) => <th scope="col" key={p.id}>{p.name}</th>)}</tr></thead>
          <tbody>
            {ready.map((r: Json) => (
              <tr key={r.id}>
                <th scope="row">{r.name}</th>
                {ready.map((c: Json) => {
                  if (r.id === c.id) return <td key={c.id}><span className="na">·</span></td>;
                  const d = cell.get(`${r.id}-${c.id}`);
                  if (!d) return <td key={c.id}><span className="na">–</span></td>;
                  const pct = d.score != null ? Math.round(15 + ((d.score - 3) / 7) * 70) : 20;
                  return (
                    <td key={c.id}>
                      <Link className={d.status} style={{ ["--pct" as string]: `${pct}%` }} to={`/p/${token}/date/${d.id}`}
                        title={`${r.name} and ${c.name}: ${d.status}`} aria-label={`${r.name} and ${c.name}: ${d.status}`}>
                        {d.status === "done" ? (d.score != null ? d.score.toFixed(0) : "✓") : d.status === "running" ? "…" : d.status === "failed" ? "!" : ""}
                      </Link>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Rankings({ token, pool }: { token: string; pool: Json }) {
  const [w, setW] = useState(0.6);
  const [data, setData] = useState<Json | null>(null);
  const [who, setWho] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const tm = useRef<number>(0);
  useEffect(() => {
    window.clearTimeout(tm.current);
    tm.current = window.setTimeout(() => api.rankings(token, w).then((d) => { setData(d); setErr(null); }).catch((e) => setErr(e.message)), 150);
    return () => window.clearTimeout(tm.current);
  }, [token, w, pool.dates_done]);
  const ids = data ? Object.keys(data.rankings).map(Number) : [];
  const names: Record<number, string> = Object.fromEntries(pool.people.map((p: Json) => [p.id, p.name]));
  const cur = who && ids.includes(who) ? who : ids[0];
  const rows: Json[] = data && cur ? data.rankings[cur] : [];

  if (err) return <Notice kind="bad">{err}</Notice>;
  if (!data) return <Skeleton h={300} />;
  if (!ids.length) return <div className="empty"><h3>No rankings yet</h3><p className="small">Rankings appear once dates have verdicts.</p></div>;

  return (
    <div className="rank">
      <nav className="who-list" aria-label="Choose a person">
        {ids.map((i) => <button key={i} aria-current={cur === i} onClick={() => setWho(i)}>{names[i]}</button>)}
      </nav>
      <div>
        <h2 style={{ fontSize: "var(--t-lg)", marginBottom: "0.25rem" }}>Best fits for {names[cur!]}</h2>
        <p className="small muted" style={{ marginBottom: "1rem" }}>Ranked from the dates, after correcting for how generously each agent scores and how broadly appealing each person is.</p>
        <div className="slider-box">
          <label htmlFor="w" className="small" style={{ fontWeight: 560 }}>How much to weigh their own taste versus mutual fit</label>
          <input id="w" type="range" min={0} max={1} step={0.05} value={w} onChange={(e) => setW(Number(e.target.value))} aria-valuetext={`${Math.round(w * 100)} percent own taste`} />
          <div className="ends"><span>Mutual fit only</span><span className="mono">{Math.round(w * 100)}% own taste</span><span>Own taste only</span></div>
        </div>
        {rows.length === 1 && (
          <div style={{ marginBottom: "1rem" }}><Notice>With two people there is only one date, so there is nothing to rank yet. Add more people, or join the 25-person demo, to get a real ranking.</Notice></div>
        )}
        <ol className="ranked">
          {rows.map((r) => (
            <li key={r.target}>
              <span className="n">{r.rank}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                  <Link to={`/p/${token}/person/${r.target}`} style={{ fontWeight: 600, color: "var(--ink)" }}>{r.target_name || names[r.target]}</Link>
                  <span className={`chip ${r.tag === "mutual" ? "good" : ""}`}>{r.tag}</span>
                  {r.conflicts?.length > 0 && <span className="chip warn">Stated values differ</span>}
                </div>
                {r.conflicts?.map((c: Json, k: number) => (
                  <div className="small" key={k} style={{ marginTop: "0.4rem", color: "var(--warn)" }}>
                    {c.topic.replace(/_/g, " ")}: “{c.a_quote}” versus “{c.b_quote}”. A small penalty ({fmt(r.penalty)}) was applied.
                  </div>
                ))}
                {r.moment?.quote && (
                  <blockquote>“{r.moment.quote}” <span className="xs">· {r.moment.reason}</span></blockquote>
                )}
                {r.mutual_composite_only && <div className="xs muted" style={{ marginTop: "0.3rem" }}>Based on date scores only, because this person joined after the others had ranked.</div>}
              </div>
              <div className="score">
                <b className="mono">{fmt(r.final)}</b>
                <span className="xs muted">you {fmt(r.own)} · them {fmt(r.their_own)}</span>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function About({ token, pool, onChange }: { token: string; pool: Json; onChange: () => void }) {
  const [d, setD] = useState<Json | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api.diagnostics(token).then(setD).catch(() => {}); }, [token, pool.dates_done]);
  const sim = d?.hypothesis?.similarity, comp = d?.hypothesis?.complement;
  const word = (x: number | null | undefined) => x == null ? "not enough data" : Math.abs(x) < 0.15 ? "almost no relationship" : x > 0 ? "a positive relationship" : "a negative relationship";
  const mine: Json[] = (pool.people as Json[]).filter((p) => (pool.new_ids || []).includes(p.id));

  async function remove(id: number) {
    if (!confirm("Delete this person and everything about them, including their dates and verdicts? This cannot be undone.")) return;
    try { await api.deletePerson(token, id); setMsg("Deleted."); onChange(); } catch (e) { setMsg((e as Error).message); }
  }
  return (
    <div style={{ display: "grid", gap: "2rem", maxWidth: "68ch" }}>
      <section className="section">
        <h2>Do similar people get along, or opposites?</h2>
        <p className="why">We tested both ideas against the dates instead of assuming either. Each number is a rank correlation (−1 to +1) across {d?.hypothesis?.n_pairs ?? "…"} directed pairs.</p>
        <dl className="cols-3">
          <div className="kv"><dt>Shared values and interests</dt><dd className="mono">{fmt(sim)}</dd><dd className="small muted">{word(sim)}</dd></div>
          <div className="kv"><dt>Complementary pace and style</dt><dd className="mono">{fmt(comp)}</dd><dd className="small muted">{word(comp)}</dd></div>
        </dl>
        <p className="small muted">With a small group these numbers move a lot. We report whatever the data shows and never tune the baselines to make an idea win.</p>
      </section>
      <section className="section">
        <h2>How much to trust this</h2>
        <ul className="hooks small">
          <li>Consistency can be measured; correctness cannot. A high rank means the two agents got along in this setup, not that two people would.</li>
          <li>Attraction cannot be measured from two public profiles, and the site does not claim to.</li>
          <li>Agents only know what is in the cited evidence. They are told to deflect on anything else, but small models can still invent a detail now and then. Read the transcripts.</li>
          <li>Each agent's scores are normalised to its own scale, and people everyone likes are discounted so they do not top every list.</li>
        </ul>
      </section>
      {mine.length > 0 && (
        <section className="section">
          <h2>Your data</h2>
          <p className="why">People you added are private to this link. Deleting removes their scrapes, photos, profile, dates and verdicts.</p>
          {mine.map((p) => (
            <div key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
              <span>{p.name || `Person ${p.id}`}</span>
              <button className="btn danger sm" onClick={() => remove(p.id)}><Trash size={16} aria-hidden /> Delete</button>
            </div>
          ))}
          {msg && <p className="small" role="status">{msg}</p>}
        </section>
      )}
      <Link to={`/p/${token}?tab=rankings`} className="small">Back to rankings <ArrowRight size={14} aria-hidden style={{ verticalAlign: "-2px" }} /></Link>
    </div>
  );
}
