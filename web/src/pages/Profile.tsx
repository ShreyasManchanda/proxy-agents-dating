import { ArrowLeft } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, initials, type Json } from "../api";
import { Claim, Notice, Skeleton, confidenceWord, flagText, refLabel } from "../components/ui";

function Block({ title, why, children }: { title: string; why?: string; children: React.ReactNode }) {
  return (
    <section className="section">
      <h2>{title}</h2>
      {why && <p className="why">{why}</p>}
      {children}
    </section>
  );
}

export default function Profile() {
  const { token = "", id = "" } = useParams();
  const [data, setData] = useState<Json | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setData(null); api.person(token, id).then(setData).catch((e) => setErr(e.message)); }, [token, id]);

  const prof: Json | null = data?.profile ?? null;
  const obs = useMemo<Record<string, Json>>(() => Object.fromEntries((prof?.observations || []).map((o: Json) => [o.id, o])), [prof]);

  if (err) return <Notice kind="bad">{err}</Notice>;
  if (!data) return <Skeleton h={400} />;
  if (!prof) return <Notice kind="warn">{data.note || "This profile is not ready yet."}</Notice>;

  const c = confidenceWord(prof.overall_confidence);
  const claims = (list?: Json[]) => (list?.length ? <ul className="claims" style={{ padding: 0 }}>{list.map((x, i) => <Claim key={i} c={x} obs={obs} />)}</ul> : null);
  const flags: string[] = (prof.source_flags || []).map(flagText).filter(Boolean);
  const v = prof.vision;
  const empty = (txt: string) => <p className="small muted">{txt}</p>;

  return (
    <>
      <p style={{ marginBottom: "1.5rem" }}><Link to={`/p/${token}`} className="small"><ArrowLeft size={14} aria-hidden style={{ verticalAlign: "-2px" }} /> All people</Link></p>
      <div className="profile">
        <aside aria-label="Summary">
          <span className="avatar" aria-hidden>{initials(prof.name)}</span>
          <div>
            <h1 style={{ fontSize: "var(--t-xl)" }}>{prof.name}</h1>
            <p className="small muted" style={{ marginTop: "0.3rem" }}>{prof.work?.summary}</p>
            {prof.identity?.location && <p className="small muted">{prof.identity.location}</p>}
          </div>
          <div className="meter">
            <div style={{ display: "flex", justifyContent: "space-between" }}><span className={`chip ${c.cls}`}>{c.word}</span><span className="mono xs muted">{Math.round((prof.overall_confidence ?? 0) * 100)}%</span></div>
            <div className="bar-track" aria-hidden><i style={{ width: `${Math.round((prof.overall_confidence ?? 0) * 100)}%` }} /></div>
            <p className="xs muted">Based on how much readable text and how many photos there were, and how well each claim is backed.</p>
          </div>
          {flags.map((f) => <Notice key={f} kind="warn">{f}</Notice>)}
          {data.note && <Notice>{data.note}</Notice>}
          {v?.n_images ? (
            <dl className="kv">
              <dt>Photos read</dt>
              <dd>{v.n_images} · {Math.round((v.group_share ?? 0) * 100)}% with other people, {Math.round((v.selfie_share ?? 0) * 100)}% selfies</dd>
            </dl>
          ) : null}
        </aside>

        <div>
          <Block title="What they are after" why="Their stated wishes come first, then what their behavior suggests. Inferred items are weakest.">
            {prof.partner_wants?.length ? (
              <ul className="claims" style={{ padding: 0 }}>
                {prof.partner_wants.map((x: Json, i: number) => (
                  <Claim key={i} c={{ ...x, claim: `${x.claim}` }} obs={obs} />
                ))}
              </ul>
            ) : null}
            {claims(prof.needs)}
            {!prof.partner_wants?.length && !prof.needs?.length && empty("Not enough signal to say what they are looking for.")}
          </Block>

          {prof.stated_signals?.length > 0 && (
            <Block title="Stated in their own words" why="Only things they wrote themselves, shown with the exact quote. Nothing here is guessed.">
              <div style={{ display: "grid", gap: "0.7rem" }}>
                {prof.stated_signals.map((s: Json, i: number) => (
                  <div className="quote-box" key={i}>
                    <span className="xs muted">{String(s.topic).replace(/_/g, " ")} · {s.source === "ig" ? "Instagram" : "LinkedIn"} · {refLabel(String(s.ref))}</span>
                    <span>“{s.quote}”</span>
                  </div>
                ))}
              </div>
            </Block>
          )}

          {([["Hobbies", prof.hobbies], ["Interests", prof.interests], ["Values", prof.values]] as [string, Json[]][])
            .filter(([, l]) => l?.length).map(([t, l]) => <Block key={t} title={t}>{claims(l)}</Block>)}
          {(() => {
            const none = ([["Hobbies", prof.hobbies], ["Interests", prof.interests], ["Values", prof.values]] as [string, Json[]][])
              .filter(([, l]) => !l?.length).map(([t]) => t.toLowerCase());
            return none.length ? <p className="small muted" style={{ padding: "1rem 0", borderTop: "1px solid var(--line)" }}>Not enough signal to say anything about their {none.join(", ")}.</p> : null;
          })()}

          {(prof.contradictions?.length > 0) && (
            <Block title="Range" why="Where the two accounts show different sides. Different, not inconsistent.">{claims(prof.contradictions)}</Block>
          )}

          <Block title="Work and background">
            <dl className="cols-3">
              <div className="kv"><dt>Now</dt><dd>{prof.work?.summary || "n/a"}</dd></div>
              {prof.work?.trajectory && <div className="kv"><dt>Path</dt><dd>{prof.work.trajectory}</dd></div>}
              {prof.education?.length > 0 && <div className="kv"><dt>Education</dt><dd>{prof.education.join("; ")}</dd></div>}
            </dl>
            {claims(prof.community_and_extras)}
          </Block>

          {(prof.communication_style || prof.lifestyle) && (
            <Block title="Style">
              <dl className="cols-3">
                {Object.entries({ ...prof.communication_style, ...prof.lifestyle }).filter(([, val]) => val && !/^(none|n\/a|unknown|unclear|not enough signal)\.?$/i.test(String(val).trim())).map(([k, val]) => (
                  <div className="kv" key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{String(val)}</dd></div>
                ))}
              </dl>
            </Block>
          )}

          {prof.conversation_hooks?.length > 0 && (
            <Block title="What to ask them about">
              <ul className="hooks">{prof.conversation_hooks.map((h: string, i: number) => <li key={i}>{h}</li>)}</ul>
            </Block>
          )}

          {prof.unknowns?.length > 0 && (
            <Block title="What the agent will not make up" why="If asked, the agent deflects instead of inventing.">
              <p className="small">{prof.unknowns.join(", ")}</p>
            </Block>
          )}
        </div>
      </div>
    </>
  );
}
