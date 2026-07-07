"""Canonical ADS-B message schema and shared types (TDD §3.1)."""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AttackType(str, Enum):
    NONE = "none"
    PATH_MOD = "path_mod"
    VELOCITY_DRIFT = "velocity_drift"
    GHOST = "ghost"


class Label(str, Enum):
    LEGIT = "legit"
    MALICIOUS = "malicious"


class AdsbMessage(BaseModel):
    """A single normalized ADS-B state vector (TDD §3.1)."""

    icao24: str
    callsign: Optional[str] = None
    ts: float  # unix epoch seconds (sensor receive time)
    lat: float
    lon: float
    geo_alt_m: float
    baro_alt_m: float
    velocity_ms: float  # reported ground speed
    heading_deg: float  # reported track angle, degrees clockwise from north
    vertical_rate_ms: float = 0.0
    nic: int = 8  # navigation integrity category
    src_sensor: str = "rx-00"

    # Ground truth — only populated by the synthetic generator (never trusted by the detector).
    truth_label: Label = Label.LEGIT
    truth_attack: AttackType = AttackType.NONE


class Detection(BaseModel):
    """Detector output for a track window (TDD §4.2)."""

    icao24: str
    label: Label
    attack_type: AttackType
    score: float  # calibrated probability in [0, 1]
    reasons: list[str] = Field(default_factory=list)
    window_end_ts: float


# --------------------------------------------------------------------------- #
# Geo helpers
# --------------------------------------------------------------------------- #

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    y = math.sin(dlmb) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlmb)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def angular_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in [0, 180]."""
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def destination_point(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Point reached travelling `dist_m` along `bearing_deg` from (lat, lon)."""
    ang = dist_m / _EARTH_RADIUS_M
    brg = math.radians(bearing_deg)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(ang) + math.cos(p1) * math.sin(ang) * math.cos(brg))
    l2 = l1 + math.atan2(
        math.sin(brg) * math.sin(ang) * math.cos(p1),
        math.cos(ang) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0
