"""Feature engineering over track windows (TDD §3.3).

The same features feed both the deterministic physics detector and the ML
baseline, so attack labels and detector logic stay aligned.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

from .schema import (
    AdsbMessage,
    angular_diff_deg,
    haversine_m,
    initial_bearing_deg,
)


@dataclass
class WindowFeatures:
    """Aggregated features for a single track window."""

    n_states: int
    span_s: float

    # Kinematic residuals — reported vs. position-implied motion.
    max_speed_residual_ms: float   # |reported speed - implied speed|
    mean_speed_residual_ms: float
    max_heading_residual_deg: float  # |reported heading - implied bearing|
    mean_heading_residual_deg: float

    # Dynamics.
    max_accel_ms2: float
    max_turn_rate_deg_s: float
    max_jump_m: float              # largest position step (teleport signal)
    max_implied_speed_ms: float

    # Altitude consistency.
    max_geo_baro_div_m: float      # |geo_alt - baro_alt|
    max_vrate_mismatch_ms: float   # |reported vrate - implied vrate|

    def to_vector(self) -> List[float]:
        return [
            self.n_states,
            self.span_s,
            self.max_speed_residual_ms,
            self.mean_speed_residual_ms,
            self.max_heading_residual_deg,
            self.mean_heading_residual_deg,
            self.max_accel_ms2,
            self.max_turn_rate_deg_s,
            self.max_jump_m,
            self.max_implied_speed_ms,
            self.max_geo_baro_div_m,
            self.max_vrate_mismatch_ms,
        ]

    @staticmethod
    def feature_names() -> List[str]:
        return [
            "n_states", "span_s",
            "max_speed_residual_ms", "mean_speed_residual_ms",
            "max_heading_residual_deg", "mean_heading_residual_deg",
            "max_accel_ms2", "max_turn_rate_deg_s",
            "max_jump_m", "max_implied_speed_ms",
            "max_geo_baro_div_m", "max_vrate_mismatch_ms",
        ]

    def as_dict(self) -> dict:
        return asdict(self)


def _safe_max(values: List[float]) -> float:
    return max(values) if values else 0.0


def _safe_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def extract(window: List[AdsbMessage]) -> WindowFeatures:
    """Compute window features from a time-ordered list of states."""
    n = len(window)
    if n < 2:
        return WindowFeatures(
            n_states=n, span_s=0.0,
            max_speed_residual_ms=0.0, mean_speed_residual_ms=0.0,
            max_heading_residual_deg=0.0, mean_heading_residual_deg=0.0,
            max_accel_ms2=0.0, max_turn_rate_deg_s=0.0,
            max_jump_m=0.0, max_implied_speed_ms=0.0,
            max_geo_baro_div_m=(abs(window[0].geo_alt_m - window[0].baro_alt_m) if n else 0.0),
            max_vrate_mismatch_ms=0.0,
        )

    speed_res: List[float] = []
    head_res: List[float] = []
    accels: List[float] = []
    turn_rates: List[float] = []
    jumps: List[float] = []
    implied_speeds: List[float] = []
    geo_baro: List[float] = [abs(window[0].geo_alt_m - window[0].baro_alt_m)]
    vrate_mismatch: List[float] = []

    prev_implied_speed = None
    for i in range(1, n):
        a, b = window[i - 1], window[i]
        dt = b.ts - a.ts
        geo_baro.append(abs(b.geo_alt_m - b.baro_alt_m))
        if dt <= 0:
            continue

        dist = haversine_m(a.lat, a.lon, b.lat, b.lon)
        implied_speed = dist / dt
        implied_bearing = initial_bearing_deg(a.lat, a.lon, b.lat, b.lon)

        jumps.append(dist)
        implied_speeds.append(implied_speed)
        speed_res.append(abs(b.velocity_ms - implied_speed))
        # Heading residual is only meaningful when actually moving.
        if implied_speed > 5.0:
            head_res.append(angular_diff_deg(b.heading_deg, implied_bearing))

        if prev_implied_speed is not None:
            accels.append(abs(implied_speed - prev_implied_speed) / dt)
        prev_implied_speed = implied_speed

        turn = angular_diff_deg(a.heading_deg, b.heading_deg)
        turn_rates.append(turn / dt)

        implied_vrate = (b.geo_alt_m - a.geo_alt_m) / dt
        vrate_mismatch.append(abs(b.vertical_rate_ms - implied_vrate))

    return WindowFeatures(
        n_states=n,
        span_s=window[-1].ts - window[0].ts,
        max_speed_residual_ms=_safe_max(speed_res),
        mean_speed_residual_ms=_safe_mean(speed_res),
        max_heading_residual_deg=_safe_max(head_res),
        mean_heading_residual_deg=_safe_mean(head_res),
        max_accel_ms2=_safe_max(accels),
        max_turn_rate_deg_s=_safe_max(turn_rates),
        max_jump_m=_safe_max(jumps),
        max_implied_speed_ms=_safe_max(implied_speeds),
        max_geo_baro_div_m=_safe_max(geo_baro),
        max_vrate_mismatch_ms=_safe_max(vrate_mismatch),
    )
