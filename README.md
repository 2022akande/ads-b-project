# ai-sysdef — ADS-B Injection Defense

An AI system that monitors live ADS-B aircraft traffic and detects injection
attacks — **path modification**, **velocity drift**, and **ghost injection** —
distinguishing legitimate traffic from malicious. Ships with a Next.js demo
dashboard and a FastAPI backend.

> Defensive research prototype. It is **software-only** — nothing is transmitted
> on any radio frequency. Not a certified safety-of-life system. See
> [docs/TDD.md](docs/TDD.md) for the full technical design.

## What it does

- Simulates realistic ADS-B traffic over a London-area airspace (OpenSky-derived
  baseline in production; procedural for the offline demo).
- Detects attacks with a **two-stage detector** (TDD §4): a deterministic
  physics-consistency layer that catches blatant attacks with human-readable
  reasons, plus a LightGBM model that corroborates and sharpens detections.
- Streams live tracks and alerts to an in-browser dashboard with a **map**,
  **track list**, **detail panel**, **alert feed**, and an **attack injector** so
  you can fire each attack type and watch the system respond.

Verified behaviour: **0% false positives** over 7k+ clean samples (4 seeds); all
three attack types reliably detected and correctly classified at demo severity.

```
ai-sysdef/
├── docs/TDD.md          # technical design document
├── backend/             # FastAPI + detector + ML pipeline   (see backend/README.md)
└── frontend/            # Next.js demo dashboard             (see frontend/README.md)
```

## Quick start

Two terminals.

**1 — Backend** (Python 3.11+):

```bash
cd backend
pip install -r requirements.txt
python -m ml.train          # optional: trains the ML model (~30s). Physics layer works without it.
python -m uvicorn app.main:app --reload --port 8000
```

**2 — Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Open http://localhost:3000. Traffic appears on the radar immediately. Use the
**Attack Injector** panel to fire a path-mod, velocity-drift, or ghost attack and
watch it light up red with an explanation in the alert feed.

## How the demo flows

1. Clean traffic populates the map (green).
2. Fire **Ghost Injection** → a phantom aircraft appears mid-airspace and is
   flagged red ("appeared mid-airspace with no plausible origin"; teleport jumps).
3. Fire **Path Modification** → a real aircraft's track bends implausibly
   ("turn rate exceeds envelope" / "heading diverges from ground track").
4. Fire **Velocity Drift** → reported speed diverges from displacement
   ("reported speed differs from position-implied speed by N m/s").

Click any track to inspect its kinematics and the model's reasoning. Adjust the
severity slider to probe the detection-vs-subtlety edge.

## Status vs. the TDD roadmap

| Milestone | State |
|-----------|-------|
| M1 Data pipeline (schema, generator) | ✅ |
| M2 Physics layer + LightGBM baseline + eval | ✅ |
| M3 Sequence model / calibration | ⏩ baseline + calibration done; temporal model is future work |
| M4 Serving (FastAPI + WebSocket) | ✅ |
| M5 Frontend demo | ✅ |
| M6 Robustness/ablation report | ⏩ basic eval in place |

See [docs/TDD.md](docs/TDD.md) §8 for the full roadmap.
