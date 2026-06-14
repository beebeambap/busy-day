"""Motif variation -> bar-aligned melody notes.

A motif is a sequence of (degree, octave_shift, rhythm_in_beats). We apply
weighted variation operations each repetition so the listener hears
recognizable but never identical phrases.
"""

from __future__ import annotations

from random import Random

VARIATIONS = ["plain", "transpose_step", "retrograde", "augment", "diminish",
              "ornament", "omit", "echo", "octave_lift", "octave_drop"]


def _variant_weights(rng: Random) -> list[float]:
    return [
        2.0,                         # plain — anchor
        1.0 + rng.random() * 0.8,    # transpose step
        0.4 + rng.random() * 0.6,    # retrograde
        0.6 + rng.random() * 0.4,    # augment (slow)
        0.5 + rng.random() * 0.4,    # diminish (fast)
        0.7 + rng.random() * 0.6,    # ornament (passing tone)
        0.5,                         # omit a note
        0.6,                         # echo (repeat last 2)
        # Octave displacement of the phrase tail. Spreads the melody's
        # spectral energy across octaves (anti-fingerprint) while
        # reading as a natural melodic leap.
        # Weights cut from original 0.7/0.5:
        #   - lift to 0.35: tail rising is musical (peak gesture)
        #   - drop to 0.15: tail diving into chord-zone (oct 3-4) was
        #     the main source of m2/M2 clashes with the left-hand
        #     chord stack — cut more aggressively than lift
        0.35,                        # octave_lift  (tail +1 oct)
        0.15,                        # octave_drop  (tail -1 oct)
    ]


def _pick_variant(rng: Random) -> str:
    weights = _variant_weights(rng)
    total = sum(weights)
    r = rng.random() * total
    cum = 0.0
    for v, w in zip(VARIATIONS, weights):
        cum += w
        if r <= cum:
            return v
    return "plain"


def apply_variation(
    motif: dict,
    variant: str,
    rng: Random,
) -> list[tuple[int, int, float]]:
    degrees = list(motif["contour"]["degrees"])
    octs    = list(motif["contour"]["octaves"])
    rhythm  = list(motif["contour"]["rhythm"])

    if variant == "plain":
        pass
    elif variant == "transpose_step":
        shift = rng.choice([-2, -1, 1, 2])
        degrees = [d + shift for d in degrees]
    elif variant == "retrograde":
        degrees, octs, rhythm = degrees[::-1], octs[::-1], rhythm[::-1]
    elif variant == "augment":
        rhythm = [r * 1.5 for r in rhythm]
    elif variant == "diminish":
        rhythm = [max(r * 0.5, 0.25) for r in rhythm]
    elif variant == "ornament" and len(degrees) > 2:
        i = rng.randrange(0, len(degrees) - 1)
        between = (degrees[i] + degrees[i + 1]) // 2 or degrees[i]
        degrees.insert(i + 1, between)
        octs.insert(i + 1, octs[i])
        # split that beat in half
        half = rhythm[i] / 2
        rhythm[i] = half
        rhythm.insert(i + 1, half)
    elif variant == "omit" and len(degrees) > 3:
        i = rng.randrange(1, len(degrees) - 1)
        # merge omitted note's duration into previous
        rhythm[i - 1] += rhythm[i]
        del degrees[i]; del octs[i]; del rhythm[i]
    elif variant == "echo":
        n = min(2, len(degrees))
        degrees += degrees[-n:]
        octs    += octs[-n:]
        rhythm  += [r * 0.75 for r in rhythm[-n:]]
    elif variant == "octave_lift":
        # Lift the last 1-2 notes an octave — phrase-ending displacement.
        n = min(2, len(octs))
        for i in range(len(octs) - n, len(octs)):
            octs[i] += 1
    elif variant == "octave_drop":
        n = min(2, len(octs))
        for i in range(len(octs) - n, len(octs)):
            octs[i] -= 1

    return list(zip(degrees, octs, rhythm))


def fit_to_bar(
    notes: list[tuple[int, int, float]],
    bar_beats: float,
) -> list[tuple[int, int, float]]:
    """Trim or pad a motif to fit exactly `bar_beats` beats."""
    out: list[tuple[int, int, float]] = []
    used = 0.0
    for deg, oct_shift, dur in notes:
        if used + dur <= bar_beats + 1e-6:
            out.append((deg, oct_shift, dur))
            used += dur
        else:
            remaining = bar_beats - used
            if remaining > 0.125:
                out.append((deg, oct_shift, remaining))
                used = bar_beats
            break
    if used < bar_beats - 1e-6:
        # pad with rest as a sustained last note
        if out:
            d, o, r = out[-1]
            out[-1] = (d, o, r + (bar_beats - used))
        else:
            out.append((1, 0, bar_beats))
    return out


def melody_over_progression(
    rng: Random,
    motif: dict,
    progression_degrees: list[int],
    beats_per_bar: float,
) -> list[list[tuple[int, int, float]]]:
    """Return a list of bars; each bar is a list of (degree, octave_shift, dur)."""
    bars = []
    for chord_root in progression_degrees:
        variant = _pick_variant(rng)
        notes = apply_variation(motif, variant, rng)
        # transpose motif so its first note lands on a chord-tone (degree 1, 3, or 5
        # of the current chord root)
        target_offsets = [0, 2, 4]
        first_target = chord_root + rng.choice(target_offsets)
        if notes:
            shift = first_target - notes[0][0]
            notes = [(d + shift, o, r) for d, o, r in notes]
        notes = fit_to_bar(notes, beats_per_bar)
        bars.append(notes)
    return bars
