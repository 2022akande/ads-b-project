"""Track assembly and sliding-window buffers (TDD §3.2)."""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List

from .schema import AdsbMessage

WINDOW_SIZE = 30  # number of states retained per track (TDD §3.2, N=30)


class Track:
    """Time-ordered state history for a single ICAO address."""

    def __init__(self, icao24: str, window_size: int = WINDOW_SIZE) -> None:
        self.icao24 = icao24
        self.states: Deque[AdsbMessage] = deque(maxlen=window_size)

    def add(self, msg: AdsbMessage) -> None:
        self.states.append(msg)

    @property
    def latest(self) -> AdsbMessage:
        return self.states[-1]

    @property
    def window(self) -> List[AdsbMessage]:
        return list(self.states)

    def __len__(self) -> int:
        return len(self.states)


class TrackManager:
    """Assembles incoming messages into per-aircraft tracks."""

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        self.window_size = window_size
        self.tracks: Dict[str, Track] = {}

    def ingest(self, msg: AdsbMessage) -> Track:
        track = self.tracks.get(msg.icao24)
        if track is None:
            track = Track(msg.icao24, self.window_size)
            self.tracks[msg.icao24] = track
        track.add(msg)
        return track

    def active(self) -> List[Track]:
        return list(self.tracks.values())

    def prune(self, now: float, max_age_s: float = 30.0) -> List[str]:
        """Drop tracks not updated within `max_age_s`; return removed ICAOs."""
        removed = [
            icao for icao, t in self.tracks.items()
            if now - t.latest.ts > max_age_s
        ]
        for icao in removed:
            del self.tracks[icao]
        return removed

    def duplicate_icaos(self, max_pair_dist_m: float = 50_000.0) -> set[str]:
        """ICAOs whose recent positions imply two aircraft at once.

        Single-feed clone/ghost heuristic (TDD §3.3): a genuine aircraft cannot
        jump tens of km between consecutive reports. Large position jumps within a
        single ICAO's window flag a likely cloned address.
        """
        flagged: set[str] = set()
        from .schema import haversine_m

        for icao, track in self.tracks.items():
            states = track.window
            for i in range(1, len(states)):
                dt = states[i].ts - states[i - 1].ts
                if dt <= 0:
                    continue
                jump = haversine_m(
                    states[i - 1].lat, states[i - 1].lon, states[i].lat, states[i].lon
                )
                # > Mach-ish implied speed over a short gap ⇒ teleport / clone.
                if jump > max_pair_dist_m and jump / dt > 400.0:
                    flagged.add(icao)
                    break
        return flagged
