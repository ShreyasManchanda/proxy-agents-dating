// Thin typed-ish API client. Responses are loosely typed on purpose: the backend owns the schema.
export type Json = Record<string, any>;

async function req<T = Json>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try { const j = await r.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep default */ }
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  config: () => req("/api/config"),
  createPool: (pairs: { linkedin: string; instagram: string }[], add_to_demo: boolean) =>
    req("/api/pools", { method: "POST", body: JSON.stringify({ pairs, add_to_demo }) }),
  pool: (t: string) => req(`/api/pools/${t}`),
  person: (t: string, id: number | string) => req(`/api/pools/${t}/people/${id}`),
  dates: (t: string) => req<Json[]>(`/api/pools/${t}/dates`),
  date: (t: string, id: number | string) => req(`/api/pools/${t}/dates/${id}`),
  rankings: (t: string, w: number) => req(`/api/pools/${t}/rankings?own_weight=${w}`),
  diagnostics: (t: string) => req(`/api/pools/${t}/diagnostics`),
  deletePerson: (t: string, id: number) => req(`/api/pools/${t}/people/${id}`, { method: "DELETE" }),
};

export const initials = (name?: string | null) =>
  (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
