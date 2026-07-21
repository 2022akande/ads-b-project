import type { AttackType } from "./types";

// Parse a response as JSON, but never throw the opaque "Unexpected token 'I'" that
// results from calling res.json() on a non-JSON body (e.g. a bare 500 error page).
async function parseJson(res: Response) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { error: `HTTP ${res.status}: ${text.slice(0, 200) || res.statusText}` };
  }
}

// REST goes through the Next.js rewrite proxy (see next.config.mjs).
export async function injectAttack(
  attack_type: AttackType,
  severity: number,
  target_icao?: string
) {
  const res = await fetch("/api/inject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attack_type, severity, target_icao: target_icao ?? null }),
  });
  return parseJson(res);
}

export async function clearAttacks() {
  const res = await fetch("/api/clear", { method: "POST" });
  return parseJson(res);
}

export async function getModelInfo() {
  const res = await fetch("/api/model");
  return parseJson(res);
}
