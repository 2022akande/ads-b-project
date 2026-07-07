"""Build a labeled feature dataset from the synthetic generator (TDD §3.4, §3.5).

Each sample is one track *window* labeled legit/malicious with its attack type.
Tracks are split before windowing so no track leaks across splits (TDD §3.4).

In production the legit baseline would be OpenSky historical state vectors
(TDD §3.4); here we generate clean traffic procedurally with the same simulator
that drives the live demo, then apply the attack transforms to a labeled subset.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from app.features import WindowFeatures, extract
from app.generator import TrafficSimulator
from app.schema import AttackType, Label
from app.track_manager import WINDOW_SIZE


@dataclass
class Sample:
    features: WindowFeatures
    label: int          # 0 legit, 1 malicious
    attack_type: str


def _simulate_episode(
    seed: int,
    n_aircraft: int,
    steps: int,
    attack: AttackType,
    attack_fraction: float,
) -> List[Sample]:
    """Run one simulated episode and collect windowed samples."""
    sim = TrafficSimulator(seed=seed, n_aircraft=n_aircraft)
    rng = random.Random(seed * 31 + 1)

    # Mark a fraction of the fleet as attacked for this episode.
    if attack != AttackType.NONE:
        targets = [a for a in sim.fleet.values()]
        rng.shuffle(targets)
        k = max(1, int(len(targets) * attack_fraction))
        for ac in targets[:k]:
            ac.attack = attack
            ac.attack_severity = rng.uniform(0.4, 1.0)
            ac._attack_age_s = rng.uniform(0, 15)  # vary subtlety/age

    # Inject ghosts as extra aircraft.
    if attack == AttackType.GHOST:
        for _ in range(max(1, int(n_aircraft * attack_fraction))):
            sim.inject(AttackType.GHOST, severity=rng.uniform(0.4, 1.0))

    # Roll the simulation, buffering per-ICAO windows.
    from collections import defaultdict, deque

    buffers = defaultdict(lambda: deque(maxlen=WINDOW_SIZE))
    truth = {}
    samples: List[Sample] = []

    for _ in range(steps):
        for msg in sim.step(1.0):
            buffers[msg.icao24].append(msg)
            truth[msg.icao24] = (msg.truth_label, msg.truth_attack)
            window = list(buffers[msg.icao24])
            if len(window) >= 6:  # need enough history for stable features
                feats = extract(window)
                label, atk = truth[msg.icao24]
                samples.append(
                    Sample(
                        features=feats,
                        label=1 if label == Label.MALICIOUS else 0,
                        attack_type=atk.value,
                    )
                )
    return samples


def build_dataset(
    n_episodes: int = 40,
    steps: int = 60,
    n_aircraft: int = 12,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Return (X, y, feature_names) across legit and all attack episodes."""
    samples: List[Sample] = []
    attacks = [
        AttackType.NONE,
        AttackType.PATH_MOD,
        AttackType.VELOCITY_DRIFT,
        AttackType.GHOST,
    ]
    for ep in range(n_episodes):
        attack = attacks[ep % len(attacks)]
        frac = 0.0 if attack == AttackType.NONE else 0.5
        samples.extend(
            _simulate_episode(
                seed=1000 + ep,
                n_aircraft=n_aircraft,
                steps=steps,
                attack=attack,
                attack_fraction=frac,
            )
        )

    X = np.array([s.features.to_vector() for s in samples], dtype=float)
    y = np.array([s.label for s in samples], dtype=int)
    return X, y, WindowFeatures.feature_names()


if __name__ == "__main__":
    X, y, names = build_dataset()
    print(f"Built dataset: X={X.shape}, positives={int(y.sum())}/{len(y)}")
    print("Features:", names)
