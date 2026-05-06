"""Scale degree -> MIDI pitch utilities."""

from __future__ import annotations

PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Intervals (semitones from tonic) for each mode degree 1..7
MODE_INTERVALS = {
    "ionian":     [0, 2, 4, 5, 7, 9, 11],
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
    "lydian":     [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
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
) -> list[int]:
    """Build a triad/seventh from a scale degree using mode-diatonic stacking."""
    root = degree_to_midi(key_root, mode, degree, base_octave=base_octave)
    third = degree_to_midi(key_root, mode, degree + 2, base_octave=base_octave)
    fifth = degree_to_midi(key_root, mode, degree + 4, base_octave=base_octave)
    pitches = [root, third, fifth]
    if voicing == "seventh":
        pitches.append(degree_to_midi(key_root, mode, degree + 6, base_octave=base_octave))
    return pitches
