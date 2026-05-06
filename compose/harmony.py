"""Markov chord progression over scale degrees, mode-aware.

Each chord is a (degree, voicing) tuple. We never modulate inside one piece.
"""

from __future__ import annotations

from random import Random

# Per-mode transition weights between scale degrees 1..7.
# Key idea: Muji-leaning -> avoid V-I dominant cadences in dorian/mixolydian,
# prefer modal pivots (i-VII, IV-i, ii-V in ionian only).
TRANSITIONS = {
    "ionian": {
        1: {1: 0.05, 2: 0.20, 4: 0.30, 5: 0.20, 6: 0.20, 3: 0.05},
        2: {5: 0.55, 7: 0.10, 4: 0.20, 1: 0.15},
        3: {6: 0.40, 4: 0.30, 1: 0.30},
        4: {1: 0.25, 5: 0.35, 2: 0.20, 6: 0.20},
        5: {1: 0.55, 6: 0.30, 4: 0.15},
        6: {2: 0.30, 4: 0.30, 5: 0.20, 1: 0.20},
        7: {1: 0.50, 3: 0.30, 6: 0.20},
    },
    "dorian": {
        1: {7: 0.30, 4: 0.30, 2: 0.20, 6: 0.10, 1: 0.10},
        2: {5: 0.30, 1: 0.30, 4: 0.20, 7: 0.20},
        3: {6: 0.40, 2: 0.30, 1: 0.30},
        4: {1: 0.30, 7: 0.30, 5: 0.20, 2: 0.20},
        5: {1: 0.40, 4: 0.30, 7: 0.30},
        6: {2: 0.40, 5: 0.30, 1: 0.30},
        7: {1: 0.50, 4: 0.30, 6: 0.20},
    },
    "lydian": {
        1: {2: 0.30, 4: 0.20, 5: 0.20, 6: 0.20, 7: 0.10},
        2: {5: 0.50, 1: 0.30, 7: 0.20},
        3: {6: 0.40, 1: 0.30, 4: 0.30},
        4: {1: 0.30, 7: 0.30, 5: 0.20, 2: 0.20},
        5: {1: 0.50, 6: 0.30, 4: 0.20},
        6: {2: 0.40, 4: 0.30, 1: 0.30},
        7: {1: 0.50, 3: 0.30, 5: 0.20},
    },
    "mixolydian": {
        1: {7: 0.40, 4: 0.30, 5: 0.20, 6: 0.10},
        2: {5: 0.40, 1: 0.30, 7: 0.30},
        3: {6: 0.40, 4: 0.30, 1: 0.30},
        4: {1: 0.30, 7: 0.40, 5: 0.30},
        5: {1: 0.40, 4: 0.30, 7: 0.30},
        6: {2: 0.40, 4: 0.30, 1: 0.30},
        7: {1: 0.50, 4: 0.30, 6: 0.20},
    },
}


def _pick(rng: Random, dist: dict[int, float]) -> int:
    items = list(dist.items())
    total = sum(w for _, w in items)
    r = rng.random() * total
    cum = 0.0
    for deg, w in items:
        cum += w
        if r <= cum:
            return deg
    return items[-1][0]


def progression(
    rng: Random,
    mode: str,
    bars: int,
    cadence: str = "open",
) -> list[int]:
    """Returns a list of scale-degree roots, one per bar."""
    table = TRANSITIONS[mode]
    seq = [1]
    for _ in range(bars - 1):
        seq.append(_pick(rng, table[seq[-1]]))
    if cadence == "tonic":
        seq[-1] = 1
    elif cadence == "open" and seq[-1] == 1:
        seq[-1] = 4 if mode != "mixolydian" else 7
    return seq


def voicing_for_genre(genre: str) -> str:
    if genre in ("jazz_ballad", "bossa_nova"):
        return "seventh"
    return "triad"
