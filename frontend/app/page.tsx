"use client";

import { useMemo, useState } from "react";
import AirspaceMap from "@/components/AirspaceMap";
import AlertFeed from "@/components/AlertFeed";
import AttackInjector from "@/components/AttackInjector";
import TrackDetail from "@/components/TrackDetail";
import TrackList from "@/components/TrackList";
import { useStream } from "@/lib/useStream";

export default function Home() {
  const { connected, tracks, alerts, stats } = useStream();
  const [selected, setSelected] = useState<string | null>(null);

  const trackArr = useMemo(() => Array.from(tracks.values()), [tracks]);
  const selectedTrack = selected ? tracks.get(selected) ?? null : null;

  return (
    <main className="mx-auto max-w-[1400px] p-4">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">
            ai-sysdef <span className="text-radar-legit">·</span> ADS-B Injection Defense
          </h1>
          <p className="text-xs text-slate-500">
            Live detection of path modification, velocity drift, and ghost injection.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <Badge label="Stream" ok={connected} okText="live" badText="offline" />
          <Badge
            label="ML model"
            ok={!!stats?.model_loaded}
            okText="loaded"
            badText="physics-only"
          />
          <div className="text-right">
            <div className="text-slate-500">Threats</div>
            <div className="text-lg font-bold text-radar-alert">
              {stats?.malicious_tracks ?? 0}
              <span className="text-sm text-slate-500">/{stats?.total_tracks ?? 0}</span>
            </div>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <AirspaceMap tracks={trackArr} selected={selected} onSelect={setSelected} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <TrackList tracks={trackArr} selected={selected} onSelect={setSelected} />
            <TrackDetail track={selectedTrack} />
          </div>
        </div>

        <aside className="space-y-4">
          <AttackInjector targetIcao={selected} />
          <AlertFeed alerts={alerts} />
        </aside>
      </div>

      <footer className="mt-6 text-center text-[11px] text-slate-600">
        Defensive research prototype · single-feed · OpenSky-derived baseline · not a
        certified safety-of-life system.
      </footer>
    </main>
  );
}

function Badge({
  label,
  ok,
  okText,
  badText,
}: {
  label: string;
  ok: boolean;
  okText: string;
  badText: string;
}) {
  return (
    <div className="text-right">
      <div className="text-slate-500">{label}</div>
      <div className={ok ? "text-radar-legit" : "text-radar-warn"}>
        ● {ok ? okText : badText}
      </div>
    </div>
  );
}
