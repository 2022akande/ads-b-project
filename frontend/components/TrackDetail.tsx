"use client";

import { ATTACK_LABELS, TrackPayload } from "@/lib/types";

export default function TrackDetail({ track }: { track: TrackPayload | null }) {
  if (!track) {
    return (
      <div className="rounded-lg border border-radar-grid bg-radar-panel p-3 text-xs text-slate-500">
        Select a track to inspect its kinematics and the model&apos;s reasoning.
      </div>
    );
  }
  const mal = track.label === "malicious";
  return (
    <div className="rounded-lg border border-radar-grid bg-radar-panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-200">
          {track.callsign ?? track.icao24}
          <span className="ml-2 text-xs text-slate-500">{track.icao24}</span>
        </h2>
        <span className={`text-xs font-bold ${mal ? "text-radar-alert" : "text-radar-legit"}`}>
          {mal ? ATTACK_LABELS[track.attack_type] : "LEGIT"}
        </span>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-[11px]">
        <Stat label="Altitude" value={`${Math.round(track.geo_alt_m)} m`} />
        <Stat label="Speed" value={`${Math.round(track.velocity_ms)} m/s`} />
        <Stat label="Heading" value={`${Math.round(track.heading_deg)}°`} />
        <Stat label="V-rate" value={`${track.vertical_rate_ms.toFixed(1)} m/s`} />
        <Stat label="Score" value={track.score.toFixed(2)} alert={mal} />
        <Stat label="Truth" value={track.truth_attack === "none" ? "legit" : track.truth_attack} />
      </dl>

      {track.reasons.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">Why flagged</p>
          {track.reasons.map((r, i) => (
            <p key={i} className="text-[11px] leading-snug text-slate-300">• {r}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className="rounded bg-[#0c161e] p-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className={alert ? "text-radar-alert" : "text-slate-200"}>{value}</dd>
    </div>
  );
}
