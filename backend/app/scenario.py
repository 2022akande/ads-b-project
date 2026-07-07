"""Scenario engine: drives the simulator, detector, and live broadcast (TDD §5.3)."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Set

from .detector import Detector
from .generator import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, TrafficSimulator
from .schema import AdsbMessage, AttackType, Detection, Label
from .track_manager import TrackManager

TICK_SECONDS = 1.0
NEW_SPAWN_WINDOW = 8  # states during which an interior-born track is "new"


def _born_in_interior(first: AdsbMessage) -> bool:
    """True if a track's first report is well inside the airspace (no edge origin)."""
    margin = 0.25
    return (
        LAT_MIN + margin < first.lat < LAT_MAX - margin
        and LON_MIN + margin < first.lon < LON_MAX - margin
    )


class ScenarioEngine:
    """Owns the world state and the per-tick detect+broadcast pipeline."""

    def __init__(self) -> None:
        self.sim = TrafficSimulator()
        self.tracks = TrackManager()
        self.detector = Detector()
        self._subscribers: Set[asyncio.Queue] = set()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._first_seen: Dict[str, AdsbMessage] = {}
        self._seen_states: Dict[str, int] = {}
        # Aircraft already airborne when monitoring begins are the established
        # baseline — they are not "ghost spawns" even though they sit mid-airspace.
        self._established: Set[str] = set()
        self._bootstrapped = False
        self.detections_log: List[Detection] = []
        self.latest_tracks: Dict[str, dict] = {}

    # ----------------------------- lifecycle ----------------------------- #
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        self._running = False

    async def _run(self) -> None:
        while self._running:
            self.tick()
            await asyncio.sleep(TICK_SECONDS)

    # ------------------------------- core -------------------------------- #
    def tick(self) -> dict:
        """Advance one step: simulate → ingest → detect → broadcast."""
        messages = self.sim.step(TICK_SECONDS)
        now = messages[0].ts if messages else time.time()

        # First frame establishes the baseline fleet (already-airborne traffic).
        if not self._bootstrapped:
            self._established = {m.icao24 for m in messages}
            self._bootstrapped = True

        duplicate_icaos = self.tracks.duplicate_icaos()
        track_payloads: List[dict] = []
        new_detections: List[Detection] = []

        for msg in messages:
            track = self.tracks.ingest(msg)
            if msg.icao24 not in self._first_seen:
                self._first_seen[msg.icao24] = msg
            self._seen_states[msg.icao24] = self._seen_states.get(msg.icao24, 0) + 1

            is_new_spawn = (
                msg.icao24 not in self._established
                and self._seen_states[msg.icao24] <= NEW_SPAWN_WINDOW
                and _born_in_interior(self._first_seen[msg.icao24])
            )
            detection = self.detector.evaluate(
                track,
                is_duplicate_icao=msg.icao24 in duplicate_icaos,
                is_new_spawn=is_new_spawn,
            )

            payload = {
                "icao24": msg.icao24,
                "callsign": msg.callsign,
                "lat": msg.lat,
                "lon": msg.lon,
                "geo_alt_m": round(msg.geo_alt_m, 1),
                "velocity_ms": round(msg.velocity_ms, 1),
                "heading_deg": round(msg.heading_deg, 1),
                "vertical_rate_ms": round(msg.vertical_rate_ms, 1),
                "ts": msg.ts,
                "label": detection.label.value,
                "attack_type": detection.attack_type.value,
                "score": detection.score,
                "reasons": detection.reasons,
                # truth_* exposed only so the demo can show ground-truth vs. prediction.
                "truth_label": msg.truth_label.value,
                "truth_attack": msg.truth_attack.value,
            }
            track_payloads.append(payload)
            self.latest_tracks[msg.icao24] = payload

            if detection.label == Label.MALICIOUS:
                new_detections.append(detection)

        # Retire stale tracks.
        for gone in self.tracks.prune(now):
            self.latest_tracks.pop(gone, None)
            self._seen_states.pop(gone, None)
            self._first_seen.pop(gone, None)

        for d in new_detections:
            self.detections_log.append(d)
        self.detections_log = self.detections_log[-200:]

        frame = {
            "type": "frame",
            "ts": now,
            "tracks": track_payloads,
            "detections": [d.model_dump(mode="json") for d in new_detections],
            "stats": self.stats(track_payloads),
        }
        self._broadcast(frame)
        return frame

    def stats(self, track_payloads: List[dict]) -> dict:
        malicious = [t for t in track_payloads if t["label"] == "malicious"]
        by_type: Dict[str, int] = {}
        for t in malicious:
            by_type[t["attack_type"]] = by_type.get(t["attack_type"], 0) + 1
        return {
            "total_tracks": len(track_payloads),
            "malicious_tracks": len(malicious),
            "by_attack_type": by_type,
            "model_loaded": self.detector.model_meta.get("loaded", False),
        }

    # ---------------------------- pub/sub -------------------------------- #
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, frame: dict) -> None:
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()  # drop oldest for slow consumers
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass

    # ----------------------------- actions ------------------------------- #
    def inject(self, attack: AttackType, target: Optional[str], severity: float) -> dict:
        return self.sim.inject(attack, target, severity)

    def clear_attacks(self) -> int:
        return self.sim.clear_attacks()
