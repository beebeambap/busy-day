"""Features + RNG -> high-level musical decisions.

Decisions made here:
  key_root, mode, genre, bpm, meter, motif_id, signature_seed_keys
"""

from __future__ import annotations

import json
import os
from random import Random
from typing import Any

from .features import Features

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

KEYS = ["C", "D", "E", "F", "G", "A", "B"]
MODES = ["ionian", "dorian", "lydian", "mixolydian", "aeolian"]
GENRES = ["ambient", "bossa_nova", "jazz_ballad", "lo_fi", "neo_classical", "folk"]
METERS = ["3/4", "4/4", "6/8"]


def _weighted_choice(rng: Random, items: list, weights: list[float]) -> Any:
    total = sum(weights)
    r = rng.random() * total
    cum = 0.0
    for it, w in zip(items, weights):
        cum += w
        if r <= cum:
            return it
    return items[-1]


def pick_mode(rng: Random, f: Features) -> str:
    # bright → ionian/lydian; dim → dorian; warm dry → mixolydian;
    # rainy + dim + calm → aeolian (true natural minor).
    weights = [
        0.30 + 0.40 * f.brightness,                                  # ionian
        0.25 + 0.30 * (1.0 - f.brightness),                          # dorian
        0.10 + 0.30 * (f.brightness * f.calmness),                   # lydian
        0.15 + 0.30 * (f.warmth * (1.0 - f.wetness)),                # mixolydian
        0.10 + 0.45 * (f.wetness * (1.0 - f.brightness)),            # aeolian
    ]
    return _weighted_choice(rng, MODES, weights)


def pick_key(rng: Random, f: Features) -> str:
    # warm tilts to D/A, cool to E/G, wet to F
    base = {"C": 1.0, "D": 1.2, "E": 1.0, "F": 1.0, "G": 1.1, "A": 0.9, "B": 0.6}
    base["D"] += 0.5 * f.warmth
    base["A"] += 0.4 * f.warmth
    base["E"] += 0.3 * (1.0 - f.warmth)
    base["G"] += 0.3 * (1.0 - f.warmth)
    base["F"] += 0.4 * f.wetness
    items = list(base.keys())
    weights = [base[k] for k in items]
    return _weighted_choice(rng, items, weights)


def pick_genre(
    rng: Random,
    f: Features,
    avoid: list[str] | None = None,
    preferred: str | None = None,
    force: str | None = None,
) -> str:
    """Pick a genre. `force` short-circuits everything (manual override
    from the user); `preferred` is a soft +bias; `avoid` is a soft
    suppression."""
    if force and force in GENRES:
        return force

    w = {g: 1.0 for g in GENRES}
    w["ambient"] += 0.5 * f.calmness
    w["bossa_nova"] += 0.6 * f.brightness * f.warmth
    w["jazz_ballad"] += 0.5 * (f.warmth * f.wetness)
    w["lo_fi"] += 0.5 * (f.wetness * (1.0 - f.brightness))
    w["neo_classical"] += 0.4 * (1.0 - f.warmth)
    w["folk"] += 0.4 * f.brightness * (1.0 - f.wetness)

    if preferred and preferred in w:
        w[preferred] *= 2.5
    if avoid:
        for g in avoid:
            if g in w:
                w[g] *= 0.05

    items = list(w.keys())
    weights = [w[g] for g in items]
    return _weighted_choice(rng, items, weights)


def pick_bpm(rng: Random, f: Features, genre: str) -> int:
    # base from calmness: calm -> slow. Range widened so an active day
    # actually sounds active.
    center = 64 + (1.0 - f.calmness) * 36  # 64 .. 100
    if genre == "bossa_nova":
        center += 10
    elif genre == "folk":
        center += 8
    elif genre == "jazz_ballad":
        center += 2
    elif genre == "lo_fi":
        center -= 4
    elif genre == "ambient":
        center -= 2
    bpm = int(round(center + rng.uniform(-4, 4)))
    return max(60, min(112, bpm))


def pick_meter(rng: Random, genre: str) -> str:
    if genre == "bossa_nova":
        return "4/4"
    if genre == "folk":
        return _weighted_choice(rng, ["3/4", "4/4", "6/8"], [0.45, 0.4, 0.15])
    if genre == "ambient":
        return _weighted_choice(rng, ["4/4", "6/8"], [0.6, 0.4])
    return _weighted_choice(rng, METERS, [0.20, 0.65, 0.15])


def load_motifs() -> list[dict]:
    with open(os.path.join(DATA_DIR, "motifs.json"), encoding="utf-8") as fh:
        return json.load(fh)


def pick_motif(
    rng: Random,
    f: Features,
    avoid_ids: set[str] | None = None,
) -> dict:
    motifs = load_motifs()
    avoid_ids = avoid_ids or set()

    def score(m: dict) -> float:
        tags = set(m.get("tags", []))
        s = 1.0
        if "warm" in tags:           s += 0.6 * f.warmth
        if "bright" in tags:         s += 0.6 * f.brightness
        if "wet" in tags:            s += 0.6 * f.wetness
        if "sparse" in tags:         s += 0.4 * f.calmness
        if "soft" in tags:           s += 0.3 * f.calmness
        if "minor_lean" in tags:     s += 0.5 * (1.0 - f.brightness)
        if "wide_leap" in tags:      s += 0.4 * f.brightness
        if "ostinato" in tags:       s += 0.3 * f.calmness
        if "question_answer" in tags:s += 0.3 * (1.0 - f.calmness)
        if m["id"] in avoid_ids:
            s *= 0.05
        return max(s, 0.01)

    weights = [score(m) for m in motifs]
    return _weighted_choice(rng, motifs, weights)
