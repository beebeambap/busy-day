"""Curated chord progressions per intent.

When the user supplies an intent, the arranger swaps the modal Markov
generator for one of these short, hand-tuned cells. Each intent has
3-5 progressions; we pick one with the seeded RNG and loop/extend it
to fit the section length.

Degrees are 1..7 within whatever mode the song is in. The progression
"I-iii-vi-IV" is therefore stored as [1, 3, 6, 4]; in dorian it would
read i-III-VI-iv, which keeps the same modal color the intent
intended (because we also pin the mode via Intent.mode_bias).

Why hand-curate: roadmap §3 — moods are the song's "story"; the
Markov generator does fine on its own, but a curated library gives
each intent a recognisable harmonic fingerprint.
"""

from __future__ import annotations

from random import Random


INTENT_PROGRESSIONS: dict[str, list[list[int]]] = {
    "calm": [
        [1, 3, 6, 4],     # I-iii-vi-IV  (안정·순환)
        [1, 6, 4, 1],
        [1, 4, 6, 5],
        [1, 3, 4, 6],
    ],
    "warm": [
        [1, 5, 6, 4],     # I-V-vi-IV  (포근한 해결)
        [1, 4, 1, 5],
        [1, 6, 4, 5],
        [1, 5, 4, 1],
    ],
    "wistful": [
        # In dorian (intent.mode_bias) these read i-VII-VI-VII, vi-iv-i-V, etc.
        [1, 7, 6, 7],
        [6, 4, 1, 5],     # vi-IV-i-V (단조 변형)
        [1, 4, 7, 1],
        [3, 6, 4, 7],
    ],
    "lively": [
        [1, 4, 5, 1],     # I-IV-V-I  (명확한 전진)
        [1, 5, 6, 4],
        [1, 4, 6, 5],
        [1, 4, 5, 4],
    ],
    "after_rain": [
        # In mixolydian (intent.mode_bias): ♭VII reads as bVII naturally.
        [7, 4, 1, 4],     # bVII-IV-I-IV  (청량한 해방감)
        [4, 1, 7, 1],
        [1, 7, 4, 1],
        [1, 4, 7, 4],
    ],
    "sleep": [
        [1, 3, 4, 3],     # I-iii-IV-iii  (흔들림·서스펜션)
        [1, 6, 3, 4],
        [1, 3, 1, 6],
        [1, 4, 1, 3],
    ],
}


def progression_for_intent(
    intent_id: str | None,
    rng: Random,
    bars: int,
    *,
    cadence: str = "open",
    mode: str = "ionian",
) -> list[int] | None:
    """Return a degree sequence of length `bars`, looping the chosen
    progression. Returns None if the intent has no curated library so
    the caller can fall back to the Markov generator."""
    if not intent_id or intent_id not in INTENT_PROGRESSIONS:
        return None
    pool = INTENT_PROGRESSIONS[intent_id]
    base = list(rng.choice(pool))
    if not base:
        return None
    seq: list[int] = []
    while len(seq) < bars:
        seq.extend(base)
    seq = seq[:bars]
    if cadence == "tonic":
        seq[-1] = 1
    elif cadence == "open" and len(seq) >= 2 and seq[-1] == 1:
        seq[-1] = 4 if mode != "mixolydian" else 7
    return seq
