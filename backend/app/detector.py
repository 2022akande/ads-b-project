"""Two-stage detector (TDD §4).

Stage 1 — physics-consistency layer (this file): deterministic, explainable,
needs no training, runs immediately. Catches blatant path/velocity/ghost attacks
and produces human-readable reasons for the UI.

Stage 2 — ML sequence/baseline model: loaded if a trained artifact exists
(see backend/ml/train.py). When present, its calibrated probability is blended
with the physics score. When absent, the physics layer alone drives detection so
the demo is fully functional out of the box.
"""

from __future__ import annotations

import os
from typing import List, Optional

from .features import WindowFeatures, extract
from .schema import AttackType, Detection, Label
from .track_manager import Track

# --------------------------------------------------------------------------- #
# Physics thresholds — grounded in commercial-jet flight envelopes (TDD §4.1).
# --------------------------------------------------------------------------- #
SPEED_RESIDUAL_LIMIT_MS = 40.0      # reported vs implied ground speed
HEADING_RESIDUAL_LIMIT_DEG = 35.0   # reported vs implied bearing
ACCEL_LIMIT_MS2 = 12.0              # ~1.2 g longitudinal — clearly beyond airliner envelope
TURN_RATE_LIMIT_DEG_S = 6.0         # standard rate turn ≈ 3°/s; 6 is generous
TELEPORT_JUMP_M = 30_000.0          # implausible single-step position jump
MAX_PLAUSIBLE_SPEED_MS = 340.0      # ~Mach 1 near tropopause
GEO_BARO_DIV_LIMIT_M = 800.0
VRATE_MISMATCH_LIMIT_MS = 25.0


class PhysicsDetector:
    """Stage-1 deterministic detector."""

    def score(
        self,
        features: WindowFeatures,
        is_duplicate_icao: bool = False,
        is_new_spawn: bool = False,
    ) -> tuple[float, AttackType, List[str]]:
        """Return (score in [0,1], attack_type, reasons)."""
        reasons: List[str] = []
        votes: dict[AttackType, float] = {
            AttackType.PATH_MOD: 0.0,
            AttackType.VELOCITY_DRIFT: 0.0,
            AttackType.GHOST: 0.0,
        }

        # --- Velocity drift: reported speed disagrees with displacement ----- #
        if features.max_speed_residual_ms > SPEED_RESIDUAL_LIMIT_MS:
            sev = _ramp(features.max_speed_residual_ms, SPEED_RESIDUAL_LIMIT_MS, 120.0)
            votes[AttackType.VELOCITY_DRIFT] += sev
            reasons.append(
                f"reported speed differs from position-implied speed by "
                f"{features.max_speed_residual_ms:.0f} m/s "
                f"(limit {SPEED_RESIDUAL_LIMIT_MS:.0f})"
            )

        # --- Path modification: implausible turn / heading inconsistency ---- #
        if features.max_turn_rate_deg_s > TURN_RATE_LIMIT_DEG_S:
            sev = _ramp(features.max_turn_rate_deg_s, TURN_RATE_LIMIT_DEG_S, 20.0)
            votes[AttackType.PATH_MOD] += sev
            reasons.append(
                f"turn rate {features.max_turn_rate_deg_s:.1f}°/s exceeds envelope "
                f"(limit {TURN_RATE_LIMIT_DEG_S:.0f}°/s)"
            )
        if features.max_heading_residual_deg > HEADING_RESIDUAL_LIMIT_DEG:
            sev = _ramp(features.max_heading_residual_deg, HEADING_RESIDUAL_LIMIT_DEG, 120.0)
            votes[AttackType.PATH_MOD] += sev
            reasons.append(
                f"reported heading diverges from ground track by "
                f"{features.max_heading_residual_deg:.0f}°"
            )
        if features.max_accel_ms2 > ACCEL_LIMIT_MS2:
            sev = _ramp(features.max_accel_ms2, ACCEL_LIMIT_MS2, 40.0)
            votes[AttackType.PATH_MOD] += sev
            reasons.append(
                f"longitudinal acceleration {features.max_accel_ms2:.1f} m/s² "
                f"exceeds limit ({ACCEL_LIMIT_MS2:.0f})"
            )

        # --- Ghost / clone signals ------------------------------------------ #
        if features.max_jump_m > TELEPORT_JUMP_M:
            sev = _ramp(features.max_jump_m, TELEPORT_JUMP_M, 200_000.0)
            votes[AttackType.GHOST] += sev
            reasons.append(
                f"position jump of {features.max_jump_m/1000:.0f} km between reports "
                f"(teleportation)"
            )
        if features.max_implied_speed_ms > MAX_PLAUSIBLE_SPEED_MS:
            sev = _ramp(features.max_implied_speed_ms, MAX_PLAUSIBLE_SPEED_MS, 1000.0)
            votes[AttackType.GHOST] += sev
            reasons.append(
                f"implied ground speed {features.max_implied_speed_ms:.0f} m/s "
                f"exceeds physical limit"
            )
        if is_duplicate_icao:
            votes[AttackType.GHOST] += 0.9
            reasons.append("ICAO address reported from two disjoint locations (clone)")
        if is_new_spawn:
            # Legit traffic enters from the airspace boundary; a track that
            # materialises in the interior has no plausible origin (TDD §3.3).
            votes[AttackType.GHOST] += 0.6
            reasons.append("track appeared mid-airspace with no plausible origin")

        # --- Altitude consistency (supports path/velocity) ------------------ #
        if features.max_geo_baro_div_m > GEO_BARO_DIV_LIMIT_M:
            votes[AttackType.PATH_MOD] += _ramp(
                features.max_geo_baro_div_m, GEO_BARO_DIV_LIMIT_M, 3000.0
            )
            reasons.append(
                f"geometric/barometric altitude disagree by "
                f"{features.max_geo_baro_div_m:.0f} m"
            )
        if features.max_vrate_mismatch_ms > VRATE_MISMATCH_LIMIT_MS:
            votes[AttackType.VELOCITY_DRIFT] += _ramp(
                features.max_vrate_mismatch_ms, VRATE_MISMATCH_LIMIT_MS, 80.0
            )
            reasons.append(
                f"reported vertical rate inconsistent with altitude change "
                f"({features.max_vrate_mismatch_ms:.0f} m/s)"
            )

        attack_type = max(votes, key=votes.get)
        score = min(1.0, votes[attack_type])
        if score == 0.0:
            attack_type = AttackType.NONE
        return score, attack_type, reasons


def _ramp(value: float, low: float, high: float) -> float:
    """Linear severity ramp: 0 at `low`, ~1 at `high`, clamped to [0,1]."""
    if value <= low:
        return 0.0
    return min(1.0, 0.5 + 0.5 * (value - low) / max(1e-9, high - low))


class Detector:
    """Combines the physics layer with an optional trained ML model (TDD §4.1)."""

    DECISION_THRESHOLD = 0.5
    MODEL_FIRE_THRESHOLD = 0.97  # confidence required for standalone ML firing
    # With the current (deliberately blatant) synthetic attacks the physics layer
    # catches everything, so the ML model is used to *corroborate and sharpen*
    # physics detections rather than fire on its own. Standalone firing stays off
    # by default to honour the false-positive budget (TDD §1.4); enabling reliable
    # standalone ML detection needs the hard-negative mining + subtler attacks the
    # TDD calls out (§4.3, §9). Flip to True to experiment.
    ENABLE_STANDALONE_MODEL = False

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.physics = PhysicsDetector()
        self.model = None
        self.model_meta: dict = {"loaded": False}
        path = model_path or os.environ.get(
            "ASD_MODEL_PATH",
            os.path.join(os.path.dirname(__file__), "..", "ml", "model.joblib"),
        )
        self._try_load_model(path)

    def _try_load_model(self, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            import joblib  # local import: ML deps are optional

            bundle = joblib.load(path)
            self.model = bundle["model"]
            self.model_meta = {"loaded": True, **bundle.get("meta", {})}
        except Exception as exc:  # pragma: no cover - defensive
            self.model_meta = {"loaded": False, "error": str(exc)}

    def _model_prob(self, features: WindowFeatures) -> Optional[float]:
        if self.model is None:
            return None
        try:
            import numpy as np

            x = np.array([features.to_vector()], dtype=float)
            return float(self.model.predict_proba(x)[0, 1])
        except Exception:
            return None

    def evaluate(
        self,
        track: Track,
        is_duplicate_icao: bool = False,
        is_new_spawn: bool = False,
    ) -> Detection:
        features = extract(track.window)
        phys_score, attack_type, reasons = self.physics.score(
            features, is_duplicate_icao, is_new_spawn
        )

        model_prob = self._model_prob(features)
        if model_prob is not None:
            # Conservative ensemble (TDD §4.1). The physics layer is the primary
            # gate; the ML model (a) sharpens confidence once physics has flagged a
            # track, and (b) may independently fire only when *highly* confident, to
            # catch subtle attacks physics misses without breaching the FP budget.
            if phys_score >= self.DECISION_THRESHOLD:
                # Physics flagged it; the model sharpens the confidence score.
                score = max(phys_score, 0.5 + 0.5 * model_prob)
            elif self.ENABLE_STANDALONE_MODEL and model_prob >= self.MODEL_FIRE_THRESHOLD:
                score = model_prob
                if attack_type == AttackType.NONE:
                    attack_type = AttackType.PATH_MOD
                    reasons.append(f"ML model flags subtle anomaly (p={model_prob:.2f})")
            else:
                score = phys_score
        else:
            score = phys_score

        label = Label.MALICIOUS if score >= self.DECISION_THRESHOLD else Label.LEGIT
        if label == Label.LEGIT:
            attack_type = AttackType.NONE

        return Detection(
            icao24=track.icao24,
            label=label,
            attack_type=attack_type,
            score=round(score, 3),
            reasons=reasons,
            window_end_ts=track.latest.ts,
        )
