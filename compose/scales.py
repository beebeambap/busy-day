"""Scale degree -> MIDI pitch utilities."""

from __future__ import annotations

PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Intervals (semitones from tonic) for each mode degree 1..7
MODE_INTERVALS = {
    "ionian":     [0, 2, 4, 5, 7, 9, 11],
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
    "lydian":     [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "aeolian":    [0, 2, 3, 5, 7, 8, 10],   # natural minor
}


def tonic_midi(key_root: str, octave: int = 4) -> int:
    """C4 = 60. octave is the octave of the tonic note."""
    return 12 * (octave + 1) + PITCH_CLASS[key_root]


def degree_to_midi(
    key_root: str,
    mode: str,
    degree: int,
    octave_shift: int = 0,
    base_octave: int = 4,
) -> int:
    """degree is 1..7 (1 = tonic). Wraps with octave shifts as needed."""
    if degree < 1:
        return -1
    intervals = MODE_INTERVALS[mode]
    deg0 = (degree - 1) % 7
    extra_oct = (degree - 1) // 7
    semis = intervals[deg0]
    return tonic_midi(key_root, base_octave) + semis + 12 * (octave_shift + extra_oct)


def chord_pitches(
    key_root: str,
    mode: str,
    degree: int,
    voicing: str = "triad",
    base_octave: int = 3,
    spread: str = "default",
) -> list[int]:
    """Build a chord voicing from a scale degree using mode-diatonic stacking.

    Voicing kinds:
      "triad"      : root + 3rd + 5th
      "seventh"    : triad + 7th
      "ninth"      : seventh + 9th — the "tropical / café" colour the
                     CLEAR HOT tape uses. 9th = 2nd scale degree one
                     octave above the chord root.
      "open_fifth" : root + 5th (no third) — the "ancient/modal" Celtic
                     drone voicing the Muji store BGM leans on heavily
    `spread` controls the voicing's vertical span — a Muji-leaning lever
    we use to map ambient temperature to perceived warmth:
      "tight"   : everything in the same octave (cold days; close-knit)
      "default" : standard close-position stack
      "wide"    : root drops an octave, top voice rises an octave (warm
                  days; open, airy)
    """
    root = degree_to_midi(key_root, mode, degree, base_octave=base_octave)
    third = degree_to_midi(key_root, mode, degree + 2, base_octave=base_octave)
    fifth = degree_to_midi(key_root, mode, degree + 4, base_octave=base_octave)

    if voicing == "open_fifth":
        pitches = [root, fifth]
    else:
        pitches = [root, third, fifth]
        if voicing in ("seventh", "ninth"):
            pitches.append(degree_to_midi(key_root, mode, degree + 6,
                                          base_octave=base_octave))
        if voicing == "ninth":
            # 9th = 2nd scale degree, one octave above the chord root.
            # degree_to_midi handles the wrap (deg-1)//7 → extra octave.
            pitches.append(degree_to_midi(key_root, mode, degree + 8,
                                          base_octave=base_octave))

    if spread == "wide" and len(pitches) >= 2:
        pitches = list(pitches)
        pitches[0]  = pitches[0] - 12
        pitches[-1] = pitches[-1] + 12
    elif spread == "tight":
        # Already same octave by construction; nothing to do.
        pass
    return pitches
