"use client";

import { useEffect, useRef, useState } from "react";
import type { Detection, Frame, Stats, TrackPayload } from "./types";

// WebSocket connects directly to the backend (Next dev does not proxy WS reliably).
const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8000/ws/stream";

export interface StreamState {
  connected: boolean;
  tracks: Map<string, TrackPayload>;
  alerts: Detection[];
  stats: Stats | null;
}

export function useStream() {
  const [connected, setConnected] = useState(false);
  const [tracks, setTracks] = useState<Map<string, TrackPayload>>(new Map());
  const [alerts, setAlerts] = useState<Detection[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        const frame: Frame = JSON.parse(ev.data);
        setTracks((prev) => {
          const next = new Map(prev);
          for (const t of frame.tracks) next.set(t.icao24, t);
          // Drop tracks that aged out (not present in a full frame).
          if (frame.type === "frame") {
            const live = new Set(frame.tracks.map((t) => t.icao24));
            for (const k of next.keys()) if (!live.has(k)) next.delete(k);
          }
          return next;
        });
        if (frame.stats) setStats(frame.stats);
        if (frame.detections && frame.detections.length) {
          setAlerts((prev) => [...frame.detections!, ...prev].slice(0, 60));
        }
      };
    }

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  return { connected, tracks, alerts, stats };
}
