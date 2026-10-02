import { ArrowLeft } from "@phosphor-icons/react";
import { Fragment, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Json } from "../api";
import { Notice, Skeleton } from "../components/ui";

const PHASE_LABEL: Record<string, string> = { intro: "Getting to know each other", disclosure: "Going a level deeper", scenario: "A small test of fit" };
const DIM_LABEL: Record<string, string> = {
  candor_ease: "Candor and ease", mutual_enjoyment: "Mutual enjoyment", attentiveness: "Attentiveness",
  positivity: "Positivity", coordination: "Coordination", perceived_similarity: "Felt similarity",
};

/** Wraps the quoted moment from a verdict in <mark> inside the turn it came from. */
function Marked({ text, quotes }: { text: string; quotes: string[] }) {
  const q = quotes.find((x) => x && text.includes(x));
  if (!q) return <>{text}</>;
  const i = text.indexOf(q);
  return <>{text.slice(0, i)}<mark>{q}</mark>{text.slice(i + q.length)}</>;
}

export default function DateView() {
  const { token = "", id = "" } = useParams();
  const [d, setD] = useState<Json | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    const load = () => api.date(token, id).then((x) => { if (!stop) setD(x); return x; }).catch((e) => setErr(e.message));
    load().then((x) => {
      if (!x || x.status === "done" || x.status === "failed") return;
      const t = setInterval(() => load().then((y) => { if (y && y.status !== "running" && y.status !== "pending") clearInterval(t); }), 2000);
      return () => clearInterval(t);
    });
    return () => { stop = true; };
  }, [token, id]);

  if (err) return <Notice kind="bad">{err}</Notice>;
  if (!d) return <Skeleton h={400} />;

  const names: Record<string, string> = d.names;
  const nameOf = (pid: number) => names[String(pid)] || `Person ${pid}`;
  const firstId = d.transcript[0]?.speaker;
  const byRater: Record<number, Json[]> = {};
  d.verdicts.forEach((v: Json) => { (byRater[v.from] ||= []).push(v); });
  const quotes = d.verdicts.map((v: Json) => v.quote);
  const mean = (vs: Json[], dim: string) => vs.reduce((s, v) => s + v.scores[dim], 0) / vs.length;

  let lastPhase = "";
  return (
    <>
      <p style={{ marginBottom: "1.5rem" }}><Link to={`/p/${token}?tab=grid`} className="small"><ArrowLeft size={14} aria-hidden style={{ verticalAlign: "-2px" }} /> Dating grid</Link></p>
      <h1 style={{ fontSize: "var(--t-xl)", marginBottom: "0.4rem" }}>{nameOf(d.a)} and {nameOf(d.b)}</h1>
      <p className="small muted" style={{ marginBottom: "2rem" }}>
        {d.status === "running" ? "This date is happening now." : d.status === "failed" ? "This date did not finish scoring." : `${d.transcript.length} turns`}
      </p>
      {d.status === "failed" && <div style={{ marginBottom: "1.5rem" }}><Notice kind="warn">One or both verdicts could not be validated, so this date is left out of the rankings until it is retried.</Notice></div>}

      <div className="date">
        <section aria-label="Transcript" className="transcript">
          {d.transcript.length === 0 && <div className="empty"><h3>Waiting for the first line</h3></div>}
          {d.transcript.map((t: Json) => {
            const side = t.speaker === firstId ? "a" : "b";
            const showPhase = t.phase !== lastPhase;
            lastPhase = t.phase;
            return (
              <Fragment key={t.i}>
                {showPhase && <div className="phase">{PHASE_LABEL[t.phase] ?? t.phase}</div>}
                <div className={`turn ${side}`}>
                  <span className="who">{t.name}</span>
                  <div className="say"><Marked text={t.text} quotes={quotes} /></div>
                </div>
              </Fragment>
            );
          })}
          {d.status === "running" && <div className="turn typing"><span className="who">…</span><div className="say">Next line coming</div></div>}
        </section>

        <aside className="verdicts" aria-label="Verdicts">
          {Object.entries(byRater).map(([rater, vs]) => (
            <div className="verdict" key={rater}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                <h3>{nameOf(Number(rater))}'s verdict</h3>
                <span className={`chip ${vs[0].second_date ? "good" : ""}`}>{vs[0].second_date ? "Wants a second date" : "No second date"}</span>
              </div>
              <ul className="dims">
                {Object.keys(DIM_LABEL).map((k) => {
                  const m = mean(vs, k);
                  return <li key={k}><span>{DIM_LABEL[k]}</span><span className="tr" aria-hidden><i style={{ width: `${m * 10}%` }} /></span><span className="mono">{m.toFixed(0)}</span></li>;
                })}
              </ul>
              <p className="small">{vs[0].reason}</p>
              <p className="small"><mark>“{vs[0].quote}”</mark></p>
            </div>
          ))}
          {d.status === "done" && <p className="xs muted">Scores are out of 10 and are normalised per agent before ranking. The highlighted line in the transcript is the moment each agent said mattered most.</p>}
        </aside>
      </div>
    </>
  );
}
