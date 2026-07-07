# Technical Design Document — ADS-B Injection Defense AI

**Project codename:** `ai-sysdef`
**Status:** Draft v1.0
**Last updated:** 2026-06-30
**Author:** Engineering

---

## 1. Overview

### 1.1 Problem statement

Automatic Dependent Surveillance–Broadcast (ADS-B) is the backbone of modern
air-traffic surveillance. Aircraft continuously broadcast their identity,
position, velocity, and altitude over unauthenticated, unencrypted 1090 MHz
(1090ES) and 978 MHz (UAT) data links. Because the protocol has **no
authentication, no integrity check, and no encryption**, any party with a
software-defined radio (SDR) can transmit forged messages that ground stations
and nearby aircraft will accept as genuine.

This exposes three classes of attack we explicitly defend against:

| Attack | Description | Observable signature |
|--------|-------------|----------------------|
| **Path modification** | Attacker alters reported lat/long of a real aircraft, bending its apparent track. | Kinematically implausible turns, position jumps, off-airway drift, mismatch with multilateration. |
| **Velocity drift** | Attacker spoofs velocity/heading vectors so reported speed diverges from true displacement. | Reported velocity inconsistent with derived position delta over time; impossible acceleration. |
| **Ghost injection** | Attacker fabricates aircraft that do not exist ("ghosts"), or clones an ICAO address. | Targets with no plausible origin, duplicate ICAO addresses, missing RF/sensor corroboration, teleportation. |

### 1.2 Goal

Build an AI system that ingests an ADS-B message stream, classifies each track as
**legitimate** or **malicious** (and labels the attack sub-type), and surfaces
detections in an in-browser demo dashboard. The system is a *defensive,
detect-and-alert* tool — it does not transmit, jam, or otherwise interact with
the RF environment.

### 1.3 Non-goals

- Not a certified or operational ATC safety system; this is a research/demo prototype.
- No RF transmission, jamming, or active countermeasures.
- No hardware SDR capture in v1 (recorded/synthetic feeds); a live SDR
  adapter is a stretch goal.
- **Single-feed only in v1** — no multi-sensor / multilateration corroboration.
  Detection relies on intra-track kinematic and identity signals; multi-feed
  corroboration is deferred to v2.
- Not a general anomaly detector for non-ADS-B telemetry.

### 1.4 Success criteria

- **Detection quality:** ≥ 0.95 ROC-AUC distinguishing legit vs. malicious tracks
  on the held-out test set; per-class recall ≥ 0.90 for each of the three attack types.
- **False-positive budget:** ≤ 2% of legitimate tracks flagged over a representative replay.
- **Latency:** per-message scoring p95 < 50 ms; end-to-end alert (ingest → UI) < 1 s.
- **Demo:** a reviewer can load a scenario in the browser, watch live tracks on a
  map, trigger each attack type, and see the model flag it with an explanation.

---

## 2. System architecture

### 2.1 High-level diagram

```
                       ┌──────────────────────────────────────────────┐
                       │                  Data sources                 │
                       │  • Recorded ADS-B (OpenSky / dump1090 JSON)    │
                       │  • Synthetic attack generator (path/vel/ghost) │
                       └───────────────┬──────────────────────────────┘
                                       │  raw messages
                                       ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                        Ingestion service                       │
        │  normalize → dedupe → per-ICAO track assembly → feature buffer  │
        └───────────────┬───────────────────────────────────────────────┘
                        │ feature windows
                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                     Inference service (ML)                      │
        │  physics-consistency checks  +  sequence model (per-track)      │
        │  → {label, attack_type, score, contributing_features}           │
        └───────────────┬───────────────────────────────────────────────┘
                        │ scored tracks + alerts
                        ▼
        ┌───────────────────────────┐        ┌──────────────────────────┐
        │      Backend API (FastAPI)│◀──────▶│  WebSocket / SSE stream   │
        │  REST: scenarios, history │        │  live tracks + detections │
        └───────────────┬───────────┘        └────────────┬─────────────┘
                        │                                  │
                        ▼                                  ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                  Next.js frontend (demo)                        │
        │  live map • track list • alert feed • attack injector • replay  │
        └───────────────────────────────────────────────────────────────┘
```

### 2.2 Components

1. **Data layer** — recorded ADS-B corpora + a synthetic attack generator that
   takes clean tracks and injects path/velocity/ghost perturbations with ground-truth labels.
2. **Ingestion service** — normalizes heterogeneous message formats into a canonical
   schema, assembles per-aircraft tracks (keyed by ICAO 24-bit address), and maintains
   sliding feature windows.
3. **Inference service** — a two-stage detector: a fast deterministic
   physics-consistency layer, followed by an ML sequence model that scores the track.
4. **Backend API** — FastAPI service exposing REST endpoints (scenario control,
   history, model metadata) and a streaming channel (WebSocket/SSE) pushing live
   tracks and detections to the UI.
5. **Frontend** — Next.js app: map visualization, track table, alert feed, and an
   "attack injector" panel for the demo.

---

## 3. Data design

### 3.1 Canonical message schema

Every incoming message is normalized to:

```jsonc
{
  "icao24": "a1b2c3",        // 24-bit ICAO address (hex)
  "callsign": "UAL123",      // may be null
  "ts": 1719740400.123,      // unix epoch seconds (sensor receive time)
  "lat": 51.4700,            // degrees, may be null on velocity-only msgs
  "lon": -0.4543,
  "geo_alt_m": 11277.6,      // geometric altitude
  "baro_alt_m": 11300.0,     // barometric altitude
  "velocity_ms": 250.3,      // ground speed
  "heading_deg": 287.5,
  "vertical_rate_ms": 0.0,
  "nic": 8,                  // navigation integrity category (when present)
  "src_sensor": "rx-07"      // receiver id, for multi-sensor corroboration
}
```

### 3.2 Track assembly

Messages are grouped by `icao24` into **tracks**. A track is a time-ordered
sequence of message states. The detector operates on a **sliding window** of the
last *N* states (default N = 30, ~30–60 s depending on update rate) so it can reason
about temporal consistency rather than a single point.

### 3.3 Feature engineering

Derived per step within a window:

- **Kinematic residuals** — difference between *reported* velocity/heading and the
  velocity/heading *implied* by consecutive positions (great-circle displacement / Δt).
  This is the core signal for **velocity drift** and **path modification**.
- **Acceleration & turn rate** — first/second derivatives; flag values exceeding the
  flight envelope of the aircraft category.
- **Altitude consistency** — geometric vs. barometric divergence; vertical rate vs.
  altitude delta.
- **Positional plausibility** — distance from nearest airway/known traffic lanes,
  jump distance between consecutive fixes (teleportation detection for **ghosts**).
- **Cross-sensor corroboration** — *deferred (multi-feed, v2).* v1 is **single-feed**,
  so ghost detection relies on intra-track signals instead: implausible spawn points,
  teleportation jumps, duplicate ICAO addresses active in disjoint locations, and
  cadence anomalies. The `src_sensor` field remains in the schema so multi-sensor
  corroboration can be added later without a data-model change.
- **Identity features** — duplicate ICAO addresses active simultaneously in
  disjoint locations (clone/ghost signature); callsign/ICAO consistency.
- **Message-rate / cadence features** — inter-arrival jitter; injected traffic often
  has machine-regular or anomalous cadence.

### 3.4 Datasets

| Set | Source | Purpose |
|-----|--------|---------|
| `legit_real` | **OpenSky Network** historical state-vector data | Clean baseline of real traffic (primary source). |
| `legit_sim` | BlueSky / custom flight-dynamics sim | Augment edge cases (holds, missed approaches). |
| `attack_synth` | Synthetic generator (§3.5) | Labeled path/velocity/ghost attacks. |

**Primary data source — OpenSky Network.** v1 uses OpenSky historical
state-vector records as the legitimate-traffic baseline (pulled via the OpenSky
REST API / historical database, subject to its research terms of use). All
synthetic attacks (§3.5) are derived by perturbing OpenSky-sourced clean tracks,
so attack and legit data share the same realistic statistical distribution.

Split: 70 / 15 / 15 train/val/test, **split by track and by time window** (no track
appears in two splits) to prevent leakage.

### 3.5 Synthetic attack generator

A deterministic, seeded module that takes a clean track and produces a labeled
malicious variant:

- **Path modification:** apply a smooth lateral offset / injected turn to a segment
  of lat/lon while keeping it locally smooth (the hard case — abrupt jumps are trivial).
- **Velocity drift:** scale/bias the reported velocity & heading fields while leaving
  true position progression intact (or vice-versa), creating reported-vs-implied divergence.
- **Ghost injection:** synthesize a brand-new track from a fake spawn point, or clone
  an existing ICAO with an offset trajectory.

Each generated message carries ground-truth labels `is_malicious` and `attack_type`
plus an `attack_severity` (subtle → blatant) so we can measure detection vs. subtlety.

---

## 4. Model design

### 4.1 Two-stage detector

**Stage 1 — Physics-consistency layer (deterministic).**
Cheap, explainable rules grounded in flight dynamics: reported-vs-implied velocity
residual, impossible acceleration/turn-rate, teleportation jumps, duplicate ICAO,
altitude inconsistency. Catches blatant attacks instantly and produces
human-readable reasons. Outputs a feature vector + preliminary flags consumed by Stage 2.

**Stage 2 — ML sequence model.**
Operates on the windowed feature sequence to catch *subtle, slow* manipulations the
rule layer misses (e.g. a gradual path bend within envelope).

- **Baseline:** Gradient-Boosted Trees (XGBoost/LightGBM) on aggregated window features
  — strong, fast, interpretable; our first milestone and the bar to beat.
- **Primary:** a temporal model over the sequence — **1D-CNN or small Transformer
  encoder** producing (a) a binary legit/malicious head and (b) a 3-way attack-type head
  (path / velocity / ghost). Multi-task so the type head sharpens the binary head.
- **Auxiliary unsupervised:** an autoencoder / one-class model trained on *legit only*,
  scoring reconstruction error. Catches novel attack patterns not in the synthetic set
  and guards against overfitting to the generator.

Final decision = calibrated ensemble of physics flags + supervised score + anomaly score.

### 4.2 Inputs / outputs

**Input:** sliding window of *N* canonical states for one track + derived features.

**Output:**
```jsonc
{
  "icao24": "a1b2c3",
  "label": "malicious",            // "legit" | "malicious"
  "attack_type": "path_mod",       // "none"|"path_mod"|"velocity_drift"|"ghost"
  "score": 0.93,                   // calibrated probability
  "reasons": [                     // explainability for the UI
    "reported velocity 250 m/s vs implied 180 m/s (residual 70)",
    "turn rate 9°/s exceeds envelope for class A320"
  ],
  "window_end_ts": 1719740400.123
}
```

### 4.3 Training

- **Loss:** binary cross-entropy (legit/malicious) + categorical cross-entropy
  (attack type), weighted; class-balanced sampling because legit ≫ malicious.
- **Calibration:** temperature/Platt scaling on the validation set so `score`
  reflects true probability (matters for the false-positive budget).
- **Hard-negative mining:** feed legit edge cases (sharp legitimate turns, holding
  patterns, climb/descent) to suppress false positives.
- **Frameworks:** PyTorch for the sequence model; LightGBM for the baseline;
  scikit-learn for preprocessing/metrics. Experiment tracking via MLflow (or
  Weights & Biases).

### 4.4 Evaluation

- Primary: ROC-AUC, PR-AUC (PR matters under class imbalance), per-class
  precision/recall/F1, confusion matrix.
- Operational: false-positive rate over a full legit replay; detection latency
  (windows-to-detect) vs. attack severity.
- Robustness: evaluate against *held-out attack parameterizations* not seen in
  training (e.g. unseen offset magnitudes) to test generalization beyond the generator.
- Ablations: physics-layer-only vs. ML-only vs. ensemble.

---

## 5. Backend / serving design

### 5.1 Stack

- **Language/runtime:** Python 3.11.
- **API framework:** FastAPI (async) + Uvicorn.
- **Streaming:** WebSocket (primary) with SSE fallback for live track/alert push.
- **Model serving:** in-process for the demo (load model at startup); pluggable to
  an ONNX-runtime or TorchServe endpoint later.
- **Storage:** SQLite/Parquet for scenario replays and detection history in the demo;
  swappable for Postgres/TimescaleDB in a fuller deployment.

### 5.2 Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/scenarios` | List available demo scenarios. |
| `POST` | `/api/scenarios/{id}/start` | Begin replaying a scenario into the live stream. |
| `POST` | `/api/inject` | Inject an attack (type, target ICAO, severity) into the running stream — drives the demo. |
| `GET` | `/api/tracks` | Current snapshot of active tracks + latest scores. |
| `GET` | `/api/detections` | Detection/alert history for the running scenario. |
| `GET` | `/api/model` | Model version, metrics, thresholds. |
| `WS` | `/ws/stream` | Push: track updates + detection events in real time. |

### 5.3 Data flow at runtime

1. Scenario player (or live adapter) emits canonical messages onto an internal queue.
2. Ingestion assembles tracks, updates sliding windows, emits feature windows.
3. Inference scores each updated window, attaches reasons.
4. Scored tracks + any new detections are persisted and broadcast over the WebSocket.
5. Frontend renders updates; alerts animate in the feed and highlight on the map.

---

## 6. Frontend design (Next.js)

### 6.1 Stack

- **Framework:** Next.js (App Router) + React + TypeScript.
- **Map:** MapLibre GL JS (open) or Leaflet; aircraft rendered as rotated markers
  along their tracks, malicious tracks colored/outlined distinctly.
- **State/data:** TanStack Query for REST; a thin WebSocket client hook for the live stream.
- **Styling/UI:** Tailwind CSS + a component kit (shadcn/ui).
- **Charts:** lightweight (Recharts/visx) for residual/score time-series.

### 6.2 Key views

1. **Live map** — real-time aircraft positions and trails; legit vs. malicious color
   coding; click a track to open a detail drawer.
2. **Track detail drawer** — kinematics, the model's `score`, `attack_type`, and the
   `reasons` list; a sparkline of velocity-residual / anomaly score over the window.
3. **Alert feed** — chronological detections with type, confidence, and target ICAO.
4. **Attack injector panel** — the demo centerpiece: choose attack type
   (path / velocity / ghost), target, and severity, fire it, and watch the model
   respond. Makes the defense legible to a non-expert reviewer.
5. **Scenario controls** — pick/replay scenarios, play/pause/seek, adjust the
   detection threshold live to show the precision/recall trade-off.

### 6.3 Demo UX flow

Load scenario → clean traffic populates the map → reviewer fires a "ghost injection"
→ a phantom aircraft appears → within seconds the model flags it red with a reason
("no cross-sensor corroboration; spawn with no plausible origin") → alert lands in
the feed. Repeat for path-mod and velocity-drift to show all three detectors.

---

## 7. Tech stack summary

| Layer | Choice |
|-------|--------|
| Data / ML | Python 3.11, PyTorch, LightGBM, scikit-learn, NumPy/Pandas, MLflow |
| Synthetic data | Custom seeded generator (+ optional BlueSky for flight dynamics) |
| Backend | FastAPI, Uvicorn, WebSocket/SSE |
| Storage | SQLite / Parquet (demo); Postgres/TimescaleDB (future) |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind, MapLibre/Leaflet, TanStack Query |
| Tooling | Docker Compose (local orchestration), pytest, ESLint/Prettier |

---

## 8. Milestones

| # | Milestone | Deliverable |
|---|-----------|-------------|
| M1 | Data pipeline | Ingestion + canonical schema + synthetic attack generator with labels. |
| M2 | Baseline detector | Physics-consistency layer + LightGBM baseline; eval harness & metrics. |
| M3 | Sequence model | Temporal multi-task model; ensemble; calibration; hits target metrics. |
| M4 | Serving | FastAPI + WebSocket streaming; scenario player + inject endpoint. |
| M5 | Frontend | Next.js demo: map, track detail, alert feed, attack injector. |
| M6 | Polish & eval | Robustness/ablation report, false-positive tuning, demo scenarios, docs. |

---

## 9. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Model overfits the synthetic generator and fails on real attacks. | Held-out attack parameterizations; unsupervised anomaly head trained on legit-only; diverse generator parameters. |
| High false-positive rate erodes trust. | Calibrated scores, hard-negative mining, explicit FP budget in eval, adjustable threshold in UI. |
| Real ADS-B data is messy (dropouts, multipath, NIC gaps). | Robust track assembly, missing-value handling, cross-sensor logic tolerant to gaps. |
| Subtle path/velocity attacks evade physics rules. | That is exactly why Stage 2 (temporal ML) exists; measure detection vs. severity. |
| Demo latency makes the live story unconvincing. | In-process serving, windowed incremental features, p95 latency budget enforced. |
| Scope creep into live SDR / operational claims. | Explicit non-goals (§1.3); SDR is a clearly-marked stretch goal. |

### 9.1 Ethical & safety note

This is a **defensive detection** prototype. It does not transmit on aviation
frequencies, jam, or generate spoofed traffic onto any real RF medium — the
synthetic attack generator operates purely on in-software datasets. Real-world ADS-B
spoofing is illegal in most jurisdictions; this project targets detection and
research only and must not be represented as a certified safety-of-life system.

---

## 10. Open questions

- ~~Which real-data corpus do we use for the legit baseline?~~ **Decided: OpenSky
  Network historical state-vector data (§3.4).**
- ~~Do we need multi-sensor corroboration in v1?~~ **Decided: no — v1 is single-feed;
  multi-sensor corroboration deferred to v2 (§1.3, §3.3).**
- Transformer vs. 1D-CNN for the sequence head — decide after the M2 baseline.
- Do we ship the live SDR (dump1090) adapter as a stretch goal, or keep v1 replay-only?
