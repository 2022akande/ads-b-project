"use client";

import { ATTACK_LABELS, TrackPayload } from "@/lib/types";

export default function TrackList({
  tracks,
  selected,
  onSelect,
}: {
  tracks: TrackPayload[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const sorted = [...tracks].sort((a, b) => b.score - a.score);
  return (
    <div className="rounded-lg border border-radar-grid bg-radar-panel p-3">
      <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-slate-300">
        Tracks ({tracks.length})
      </h2>
      <div className="max-h-[340px] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500">
            <tr className="text-left">
              <th className="py-1">Callsign</th>
              <th>Alt</th>
              <th>Spd</th>
              <th>Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t) => {
              const mal = t.label === "malicious";
              return (
                <tr
                  key={t.icao24}
                  onClick={() => onSelect(t.icao24)}
                  className={`cursor-pointer border-t border-radar-grid/50 hover:bg-[#13202b] ${
                    selected === t.icao24 ? "bg-[#13202b]" : ""
                  }`}
                >
                  <td className="py-1 text-slate-200">{t.callsign ?? t.icao24}</td>
                  <td className="text-slate-400">{Math.round(t.geo_alt_m)}</td>
                  <td className="text-slate-400">{Math.round(t.velocity_ms)}</td>
                  <td className={mal ? "text-radar-alert" : "text-slate-500"}>
                    {t.score.toFixed(2)}
                  </td>
                  <td>
                    {mal ? (
                      <span className="text-radar-alert">{ATTACK_LABELS[t.attack_type]}</span>
                    ) : (
                      <span className="text-radar-legit">legit</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
