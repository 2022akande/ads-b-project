"use client";

import { useState } from "react";
import { clearAttacks, injectAttack } from "@/lib/api";
import { AttackType, ATTACK_LABELS } from "@/lib/types";

const ATTACKS: AttackType[] = ["path_mod", "velocity_drift", "ghost"];

export default function AttackInjector({ targetIcao }: { targetIcao: string | null }) {
  const [severity, setSeverity] = useState(0.85);
  const [last, setLast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function fire(attack: AttackType) {
    setBusy(true);
    // Ghosts spawn fresh; path/velocity attacks target the selected (or a random) aircraft.
    const target = attack === "ghost" ? undefined : targetIcao ?? undefined;
    const res = await injectAttack(attack, severity, target);
    setBusy(false);
    if (res.error) setLast(`Error: ${res.error}`);
    else setLast(`Injected ${ATTACK_LABELS[attack]} → ${res.callsign ?? res.icao24}`);
  }

  async function clear() {
    setBusy(true);
    const res = await clearAttacks();
    setBusy(false);
    setLast(`Cleared ${res.cleared} attack(s)`);
  }

  return (
    <div className="rounded-lg border border-radar-grid bg-radar-panel p-3">
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-radar-warn">
        Attack Injector
      </h2>
      <p className="mb-3 text-xs text-slate-400">
        Software-only simulation — nothing is transmitted on any radio frequency.
        {targetIcao ? (
          <> Target: <span className="text-sky-300">{targetIcao}</span></>
        ) : (
          <> No track selected — path/velocity attacks pick a random aircraft.</>
        )}
      </p>

      <div className="mb-3 grid grid-cols-1 gap-2">
        {ATTACKS.map((a) => (
          <button
            key={a}
            disabled={busy}
            onClick={() => fire(a)}
            className="rounded border border-radar-grid bg-[#13202b] px-3 py-2 text-left text-sm text-slate-200 transition hover:border-radar-alert hover:text-white disabled:opacity-50"
          >
            ⚡ {ATTACK_LABELS[a]}
          </button>
        ))}
      </div>

      <label className="mb-1 block text-xs text-slate-400">
        Severity: <span className="text-slate-200">{severity.toFixed(2)}</span>
      </label>
      <input
        type="range"
        min={0.2}
        max={1}
        step={0.05}
        value={severity}
        onChange={(e) => setSeverity(parseFloat(e.target.value))}
        className="mb-3 w-full accent-radar-warn"
      />

      <button
        disabled={busy}
        onClick={clear}
        className="w-full rounded border border-radar-legit/40 bg-[#0e2018] px-3 py-2 text-sm text-radar-legit hover:border-radar-legit disabled:opacity-50"
      >
        Clear all attacks
      </button>

      {last && <p className="mt-2 text-xs text-slate-400">{last}</p>}
    </div>
  );
}
