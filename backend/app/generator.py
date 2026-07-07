"""Synthetic ADS-B traffic + attack generator (TDD §3.5).

For the demo this produces realistic clean traffic procedurally. The same attack
transforms are reused by the offline dataset builder (backend/ml/dataset.py) so
training data and the live demo share one source of truth.

NOTE: this is a *software-only* simulation. Nothing here transmits on any radio
frequency (TDD §9.1).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .schema import (
    AdsbMessage,
    AttackType,
    Label,
    destination_point,
)

# Demo airspace: a box around London / South-East England.
LAT_MIN, LAT_MAX = 50.8, 52.2
LON_MIN, LON_MAX = -1.4, 0.9

_CALLSIGN_PREFIXES = ["BAW", "EZY", "RYR", "VIR", "DLH", "AFR", "KLM", "UAL", "TOM"]


def _rand_icao(rng: random.Random) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(6))


def _rand_callsign(rng: random.Random) -> str:
    return f"{rng.choice(_CALLSIGN_PREFIXES)}{rng.randint(100, 999)}"


@dataclass
class Aircraft:
    """A simulated aircraft with true kinematic state."""

    icao24: str
    callsign: str
    lat: float
    lon: float
    geo_alt_m: float
    velocity_ms: float
    heading_deg: float
    vertical_rate_ms: float = 0.0
    # Active attack on this aircraft (applied at message-emit time).
    attack: AttackType = AttackType.NONE
    attack_severity: float = 0.0  # 0..1
    _attack_age_s: float = 0.0
    is_ghost: bool = False
    spawned_at: float = 0.0
    # Gentle, legitimate manoeuvring.
    _turn_bias: float = 0.0

    def advance(self, dt: float, rng: random.Random) -> None:
        """Move the aircraft forward by `dt` seconds along its true track."""
        # Occasional gentle, legitimate course/altitude changes.
        if rng.random() < 0.05:
            self._turn_bias = rng.uniform(-1.5, 1.5)  # deg/s, within envelope
        self.heading_deg = (self.heading_deg + self._turn_bias * dt) % 360.0
        if rng.random() < 0.03:
            self.vertical_rate_ms = rng.uniform(-8.0, 8.0)
        self.geo_alt_m = max(2000.0, self.geo_alt_m + self.vertical_rate_ms * dt)

        dist = self.velocity_ms * dt
        self.lat, self.lon = destination_point(self.lat, self.lon, self.heading_deg, dist)

        # High-severity ghosts intermittently teleport, exposing the
        # implausible-jump / implied-speed signal the detector keys on.
        if self.is_ghost and self.attack_severity > 0.6 and rng.random() < 0.18:
            jump_m = rng.uniform(40_000, 120_000)
            self.lat, self.lon = destination_point(
                self.lat, self.lon, rng.uniform(0, 360), jump_m
            )

        if self.attack != AttackType.NONE:
            self._attack_age_s += dt

    def emit(self, ts: float, rng: random.Random) -> AdsbMessage:
        """Produce a (possibly tampered) ADS-B message for the current state."""
        # Honest reported values with light sensor noise (~0.5 m positional).
        rep_lat = self.lat + rng.gauss(0, 5e-6)
        rep_lon = self.lon + rng.gauss(0, 5e-6)
        rep_vel = self.velocity_ms + rng.gauss(0, 0.5)
        rep_hdg = (self.heading_deg + rng.gauss(0, 0.3)) % 360.0
        rep_vrate = self.vertical_rate_ms + rng.gauss(0, 0.3)
        baro = self.geo_alt_m + rng.gauss(0, 15)

        label = Label.LEGIT
        truth = AttackType.NONE

        if self.attack == AttackType.VELOCITY_DRIFT:
            # Reported speed/heading drift away from true motion (TDD §3.5).
            label, truth = Label.MALICIOUS, AttackType.VELOCITY_DRIFT
            drift = self.attack_severity * min(1.0, self._attack_age_s / 20.0)
            rep_vel = self.velocity_ms * (1.0 + 0.9 * drift) + 60.0 * drift
            rep_hdg = (self.heading_deg + 50.0 * drift) % 360.0
            rep_vrate = self.vertical_rate_ms + 40.0 * drift

        elif self.attack == AttackType.PATH_MOD:
            # Reported position bends off the true track (TDD §3.5).
            label, truth = Label.MALICIOUS, AttackType.PATH_MOD
            ramp = min(1.0, self._attack_age_s / 25.0)
            offset_m = self.attack_severity * 4000.0 * ramp
            # Push laterally (90° off heading) to bend the apparent path.
            rep_lat, rep_lon = destination_point(
                rep_lat, rep_lon, (self.heading_deg + 90.0) % 360.0, offset_m
            )
            baro = self.geo_alt_m + self.attack_severity * 1500.0 * ramp

        elif self.attack == AttackType.GHOST:
            label, truth = Label.MALICIOUS, AttackType.GHOST

        return AdsbMessage(
            icao24=self.icao24,
            callsign=self.callsign,
            ts=ts,
            lat=rep_lat,
            lon=rep_lon,
            geo_alt_m=self.geo_alt_m,
            baro_alt_m=baro,
            velocity_ms=max(0.0, rep_vel),
            heading_deg=rep_hdg,
            vertical_rate_ms=rep_vrate,
            nic=8,
            src_sensor="rx-00",
            truth_label=label,
            truth_attack=truth,
        )


class TrafficSimulator:
    """Procedural clean-traffic generator with on-demand attack injection."""

    def __init__(self, seed: int = 7, n_aircraft: int = 12) -> None:
        self.rng = random.Random(seed)
        self.fleet: Dict[str, Aircraft] = {}
        self.t = 0.0
        for _ in range(n_aircraft):
            self._spawn_legit()

    def _spawn_legit(self) -> Aircraft:
        ac = Aircraft(
            icao24=_rand_icao(self.rng),
            callsign=_rand_callsign(self.rng),
            lat=self.rng.uniform(LAT_MIN, LAT_MAX),
            lon=self.rng.uniform(LON_MIN, LON_MAX),
            geo_alt_m=self.rng.uniform(6000, 11500),
            velocity_ms=self.rng.uniform(180, 260),
            heading_deg=self.rng.uniform(0, 360),
            vertical_rate_ms=0.0,
        )
        self.fleet[ac.icao24] = ac
        return ac

    def _spawn_legit_at_edge(self) -> Aircraft:
        """Spawn a legit aircraft on a boundary, heading into the airspace."""
        side = self.rng.choice(["N", "S", "E", "W"])
        if side == "N":
            lat, lon, hdg = LAT_MAX, self.rng.uniform(LON_MIN, LON_MAX), self.rng.uniform(135, 225)
        elif side == "S":
            lat, lon, hdg = LAT_MIN, self.rng.uniform(LON_MIN, LON_MAX), self.rng.uniform(-45, 45)
        elif side == "E":
            lat, lon, hdg = self.rng.uniform(LAT_MIN, LAT_MAX), LON_MAX, self.rng.uniform(225, 315)
        else:  # W
            lat, lon, hdg = self.rng.uniform(LAT_MIN, LAT_MAX), LON_MIN, self.rng.uniform(45, 135)
        ac = Aircraft(
            icao24=_rand_icao(self.rng),
            callsign=_rand_callsign(self.rng),
            lat=lat,
            lon=lon,
            geo_alt_m=self.rng.uniform(6000, 11500),
            velocity_ms=self.rng.uniform(180, 260),
            heading_deg=hdg % 360.0,
            vertical_rate_ms=0.0,
        )
        self.fleet[ac.icao24] = ac
        return ac

    def step(self, dt: float = 1.0) -> List[AdsbMessage]:
        """Advance the world by `dt` and return one message per aircraft."""
        self.t += dt
        msgs: List[AdsbMessage] = []
        to_remove: List[str] = []
        for icao, ac in list(self.fleet.items()):  # snapshot: spawning mutates fleet
            ac.advance(dt, self.rng)
            # Recycle aircraft that drift outside the airspace. We never flip a
            # live track's heading (an instant reversal would be an implausible
            # manoeuvre the detector would rightly flag); instead we retire the
            # track and spawn a fresh legit aircraft entering from a boundary.
            if not (LAT_MIN - 0.3 <= ac.lat <= LAT_MAX + 0.3 and
                    LON_MIN - 0.3 <= ac.lon <= LON_MAX + 0.3):
                to_remove.append(icao)
                if not ac.is_ghost:
                    self._spawn_legit_at_edge()
                continue
            msgs.append(ac.emit(self.t, self.rng))
        for icao in to_remove:
            self.fleet.pop(icao, None)
        return msgs

    # ------------------------------------------------------------------ #
    # Attack injection (drives /api/inject and the demo injector panel).
    # ------------------------------------------------------------------ #
    def inject(
        self,
        attack: AttackType,
        target_icao: Optional[str] = None,
        severity: float = 0.8,
    ) -> dict:
        """Begin an attack. Returns a summary for the API response."""
        if attack == AttackType.GHOST:
            ac = self._spawn_ghost(severity)
            return {
                "attack": attack.value,
                "icao24": ac.icao24,
                "callsign": ac.callsign,
                "severity": severity,
            }

        target = self._pick_legit_target(target_icao)
        if target is None:
            return {"error": "no eligible target aircraft"}
        target.attack = attack
        target.attack_severity = max(0.0, min(1.0, severity))
        target._attack_age_s = 0.0
        return {
            "attack": attack.value,
            "icao24": target.icao24,
            "callsign": target.callsign,
            "severity": target.attack_severity,
        }

    def clear_attacks(self) -> int:
        """Reset all aircraft to honest reporting; drop ghosts. Returns count cleared."""
        cleared = 0
        for icao in list(self.fleet):
            ac = self.fleet[icao]
            if ac.is_ghost:
                self.fleet.pop(icao, None)
                cleared += 1
            elif ac.attack != AttackType.NONE:
                ac.attack = AttackType.NONE
                ac.attack_severity = 0.0
                cleared += 1
        return cleared

    def _pick_legit_target(self, target_icao: Optional[str]) -> Optional[Aircraft]:
        if target_icao and target_icao in self.fleet:
            return self.fleet[target_icao]
        candidates = [a for a in self.fleet.values() if not a.is_ghost and a.attack == AttackType.NONE]
        return self.rng.choice(candidates) if candidates else None

    def _spawn_ghost(self, severity: float) -> Aircraft:
        # A ghost appears mid-airspace with no plausible origin.
        ac = Aircraft(
            icao24=_rand_icao(self.rng),
            callsign=_rand_callsign(self.rng),
            lat=self.rng.uniform(LAT_MIN, LAT_MAX),
            lon=self.rng.uniform(LON_MIN, LON_MAX),
            geo_alt_m=self.rng.uniform(3000, 11000),
            velocity_ms=self.rng.uniform(180, 280),
            heading_deg=self.rng.uniform(0, 360),
            attack=AttackType.GHOST,
            attack_severity=max(0.0, min(1.0, severity)),
            is_ghost=True,
            spawned_at=self.t,
        )
        # High-severity ghosts also teleport, exposing the clone/jump signal.
        ac._turn_bias = 0.0
        self.fleet[ac.icao24] = ac
        return ac
