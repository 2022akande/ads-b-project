# Backend — ai-sysdef

FastAPI service: synthetic ADS-B traffic, the two-stage detector, and a
REST + WebSocket API for the demo dashboard. Implements TDD §5.

## Run

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The live stream auto-starts. The physics-consistency detector works immediately
with no trained model.

## Train the ML model (optional)

```bash
python -m ml.train
```

Builds a labeled window dataset from the synthetic generator (TDD §3.5), trains
a calibrated LightGBM baseline (falls back to scikit-learn GBDT if LightGBM is
unavailable), and writes `ml/model.joblib`. The detector auto-loads it on the
next start and uses it to corroborate/sharpen physics detections (TDD §4.1).

## Layout

```
app/
  schema.py         # canonical ADS-B message + geo helpers (TDD §3.1)
  track_manager.py  # per-ICAO track assembly, sliding windows (TDD §3.2)
  features.py       # kinematic-residual feature engineering (TDD §3.3)
  detector.py       # Stage 1 physics layer + Stage 2 ML blend (TDD §4)
  generator.py      # procedural traffic + attack injection (TDD §3.5)
  scenario.py       # per-tick simulate→detect→broadcast pipeline (TDD §5.3)
  main.py           # FastAPI app: REST + WebSocket (TDD §5.2)
ml/
  dataset.py        # labeled dataset builder
  train.py          # LightGBM training + calibration + eval
```

## API (TDD §5.2)

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | Liveness. |
| GET  | `/api/model` | Model metadata + decision threshold. |
| GET  | `/api/tracks` | Snapshot of active tracks + latest scores. |
| GET  | `/api/detections` | Recent detection/alert history. |
| POST | `/api/inject` | Begin an attack: `{attack_type, target_icao?, severity}`. |
| POST | `/api/clear` | Reset all aircraft to honest reporting; drop ghosts. |
| POST | `/api/scenario/start` \| `/stop` | Control the live stream. |
| WS   | `/ws/stream` | Live `snapshot` then `frame` messages (tracks + detections + stats). |

## Detector design notes

- **Stage 1 (physics)** is the primary gate: deterministic, explainable, needs no
  training. Thresholds are grounded in commercial-jet flight envelopes
  (`detector.py` top constants).
- **Stage 2 (ML)** corroborates and sharpens Stage-1 detections. Standalone ML
  firing is **off by default** (`ENABLE_STANDALONE_MODEL`) because the current
  synthetic attacks are blatant enough that physics catches them, and standalone
  firing would breach the false-positive budget. Reliable standalone detection of
  *subtle* attacks needs the hard-negative mining + richer attacks the TDD calls
  out (§4.3, §9) — that's the M3 work.
- **Single-feed** (TDD §1.3): ghost detection relies on intra-track signals
  (interior spawn with no origin, teleport jumps, duplicate ICAO, cadence), not
  multi-sensor corroboration.

This is a software-only simulation (TDD §9.1) — it never transmits on any RF link.
