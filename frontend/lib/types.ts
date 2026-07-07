export type AttackType = "none" | "path_mod" | "velocity_drift" | "ghost";
export type Label = "legit" | "malicious";

export interface TrackPayload {
  icao24: string;
  callsign: string | null;
  lat: number;
  lon: number;
  geo_alt_m: number;
  velocity_ms: number;
  heading_deg: number;
  vertical_rate_ms: number;
  ts: number;
  label: Label;
  attack_type: AttackType;
  score: number;
  reasons: string[];
  truth_label: Label;
  truth_attack: AttackType;
}

export interface Detection {
  icao24: string;
  label: Label;
  attack_type: AttackType;
  score: number;
  reasons: string[];
  window_end_ts: number;
}

export interface Stats {
  total_tracks: number;
  malicious_tracks: number;
  by_attack_type: Record<string, number>;
  model_loaded: boolean;
}

export interface Frame {
  type: "frame" | "snapshot";
  ts?: number;
  tracks: TrackPayload[];
  detections?: Detection[];
  stats: Stats;
}

export const ATTACK_LABELS: Record<AttackType, string> = {
  none: "None",
  path_mod: "Path Modification",
  velocity_drift: "Velocity Drift",
  ghost: "Ghost Injection",
};

// Airspace bounds — must match backend/app/generator.py.
export const BOUNDS = { latMin: 50.8, latMax: 52.2, lonMin: -1.4, lonMax: 0.9 };
