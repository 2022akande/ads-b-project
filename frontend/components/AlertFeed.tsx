"use client";

import { ATTACK_LABELS, Detection } from "@/lib/types";

export default function AlertFeed({ alerts }: { alerts: Detection[] }) {
  return (
    <div className="rounded-lg border border-radar-grid bg-radar-panel p-3">
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-radar-alert">
        Alert Feed
      </h2>
      {alerts.length === 0 ? (
        <p className="text-xs text-slate-500">No detections yet. Inject an attack to begin.</p>
      ) : (
        <div className="max-h-[300px] space-y-2 overflow-y-auto">
          {alerts.map((a, i) => (
            <div
              key={`${a.icao24}-${a.window_end_ts}-${i}`}
              className="rounded border border-radar-alert/40 bg-[#1a1012] p-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-radar-alert">
                  {ATTACK_LABELS[a.attack_type]}
                </span>
                <span className="text-[10px] text-slate-500">
                  {a.icao24} · p={a.score.toFixed(2)}
                </span>
              </div>
              {a.reasons.slice(0, 2).map((r, j) => (
                <p key={j} className="mt-1 text-[11px] leading-snug text-slate-400">
                  • {r}
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
