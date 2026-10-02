import { CaretRight, Info, WarningCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { Json } from "../api";

export function confidenceWord(c?: number | null) {
  if (c == null) return { word: "Unknown", cls: "" };
  if (c < 0.3) return { word: "Low confidence", cls: "warn" };
  if (c < 0.55) return { word: "Medium confidence", cls: "" };
  return { word: "High confidence", cls: "good" };
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warn" | "bad"; children: ReactNode }) {
  const Icon = kind === "info" ? Info : WarningCircle;
  return (
    <div className={`notice ${kind === "info" ? "" : kind}`} role={kind === "bad" ? "alert" : undefined}>
      <Icon size={18} aria-hidden /> <div>{children}</div>
    </div>
  );
}

const FLAG_TEXT: Record<string, string> = {
  linkedin_about_empty: "LinkedIn About is empty, so there is less text to read.",
  instagram_private: "Instagram is private, so no posts could be read.",
  instagram_missing: "Instagram could not be read.",
  linkedin_missing: "LinkedIn could not be read.",
};
export const flagText = (f: string) => FLAG_TEXT[f] ?? (f.startsWith("dropped_") ? "" : f);

/** Where an observation came from, in words. */
export function refLabel(ref: string): string {
  if (ref === "bio") return "Instagram bio";
  if (ref.startsWith("p:")) return "Instagram post";
  if (ref === "about") return "LinkedIn About";
  if (ref === "headline") return "LinkedIn headline";
  if (ref.startsWith("exp:")) return `LinkedIn role ${Number(ref.slice(4)) + 1}`;
  if (ref.startsWith("edu:")) return "LinkedIn education";
  if (ref.startsWith("post:")) return "LinkedIn post";
  if (ref.startsWith("amplified:")) return "LinkedIn reshare";
  if (ref === "skills") return "LinkedIn skills";
  return ref;
}

/** A claim that expands to the observations it cites. */
export function Claim({ c, obs }: { c: Json; obs: Record<string, Json> }) {
  const ev: Json[] = (c.evidence || []).map((id: string) => obs[id]).filter(Boolean);
  return (
    <li className="claim" style={{ listStyle: "none" }}>
      <details className="claim">
        <summary>
          <span className="ct">{c.claim}</span>
          <span className="conf" title="How strongly the cited evidence supports this">
            {Math.round((c.confidence ?? 0) * 100)}% <CaretRight size={12} aria-hidden />
          </span>
        </summary>
        <div className="evid">
          {ev.length === 0 && <span className="muted">No evidence attached.</span>}
          {ev.map((o) => (
            <div key={o.id}>
              <div>{o.text}</div>
              <div className="src">{refLabel(String(o.ref))} · {o.source === "ig" ? "Instagram" : "LinkedIn"} · {o.kind}</div>
            </div>
          ))}
        </div>
      </details>
    </li>
  );
}

export const Skeleton = ({ h = 16, w = "100%" }: { h?: number; w?: string | number }) => (
  <div className="skeleton" style={{ height: h, width: w }} aria-hidden />
);

export const fmt = (x?: number | null, d = 2) => (x == null ? "n/a" : x.toFixed(d));
