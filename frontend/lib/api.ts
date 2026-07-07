import type { AttackType } from "./types";

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
  return res.json();
}

export async function clearAttacks() {
  const res = await fetch("/api/clear", { method: "POST" });
  return res.json();
}

export async function getModelInfo() {
  const res = await fetch("/api/model");
  return res.json();
}
