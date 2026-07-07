"use client";

import { BOUNDS, TrackPayload } from "@/lib/types";

const W = 720;
const H = 440;

// Equirectangular projection of the airspace box onto the SVG canvas (offline,
// no tile server — TDD §6.1). Good enough at this small scale for the demo.
function project(lat: number, lon: number): [number, number] {
  const x = ((lon - BOUNDS.lonMin) / (BOUNDS.lonMax - BOUNDS.lonMin)) * W;
  const y = (1 - (lat - BOUNDS.latMin) / (BOUNDS.latMax - BOUNDS.latMin)) * H;
  return [x, y];
}

function Plane({ t, onSelect, selected }: { t: TrackPayload; onSelect: (id: string) => void; selected: boolean }) {
  const [x, y] = project(t.lat, t.lon);
  const malicious = t.label === "malicious";
  const color = malicious ? "#ff4d4f" : "#39d98a";
  return (
    <g
      transform={`translate(${x},${y})`}
      onClick={() => onSelect(t.icao24)}
      style={{ cursor: "pointer" }}
    >
      {malicious && (
        <circle r={16} fill="none" stroke={color} strokeWidth={1.5} className="animate-alert" />
      )}
      {selected && <circle r={20} fill="none" stroke="#7cc7ff" strokeWidth={1} />}
      <g transform={`rotate(${t.heading_deg})`}>
        <path d="M0,-8 L5,7 L0,4 L-5,7 Z" fill={color} stroke="#0a0f14" strokeWidth={0.5} />
      </g>
      <text x={8} y={4} fontSize={9} fill={malicious ? "#ff8385" : "#9fb3c2"}>
        {t.callsign ?? t.icao24}
      </text>
    </g>
  );
}

export default function AirspaceMap({
  tracks,
  selected,
  onSelect,
}: {
  tracks: TrackPayload[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const gridLines = [];
  for (let i = 1; i < 6; i++) {
    gridLines.push(<line key={`v${i}`} x1={(W / 6) * i} y1={0} x2={(W / 6) * i} y2={H} stroke="#1b2a36" strokeWidth={1} />);
    gridLines.push(<line key={`h${i}`} x1={0} y1={(H / 6) * i} x2={W} y2={(H / 6) * i} stroke="#1b2a36" strokeWidth={1} />);
  }

  return (
    <div className="rounded-lg border border-radar-grid bg-radar-panel p-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Airspace radar">
        <rect x={0} y={0} width={W} height={H} fill="#0a0f14" />
        {gridLines}
        <text x={8} y={16} fontSize={10} fill="#3d5566">
          LON {BOUNDS.lonMin}° → {BOUNDS.lonMax}° · LAT {BOUNDS.latMin}° → {BOUNDS.latMax}°
        </text>
        {tracks.map((t) => (
          <Plane key={t.icao24} t={t} onSelect={onSelect} selected={selected === t.icao24} />
        ))}
      </svg>
    </div>
  );
}
