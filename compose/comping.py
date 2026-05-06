"""Genre-aware harmony comping + bass walking patterns.

Each pattern is expressed as a list of (start_beat, dur, voice_kind,
vel_mult). It runs *inside one bar* — the arranger applies it for every
non-final bar so the left hand actually plays through the form instead
of holding a single block chord.

Voice kinds (for harmony):
  "all"      — full chord (root + 3rd + 5th [+ 7th if seventh voicing])
  "top"      — 3rd + 5th [+ 7th]   (no root)
  "top3"     — top three voices    (3rd + 5th + 7th if seventh, else
                                    3rd + 5th)
  "root"     — root only
  "fifth"    — 5th only
  "root_5"   — root + 5th
  "alberti_a"  / "alberti_b" — alternating cell for arpeggio comping

Voice kinds (for bass):
  "root"     — chord root, low octave
  "fifth"    — chord 5th, low octave
  "third"    — chord 3rd, low octave
  "fifth_up" — 5th one octave above the bass register (alberti pattern)
"""

from __future__ import annotations


# ── harmony per (genre, beats_per_bar) ─────────────────────────────
_H44 = {
    "ambient": [
        (0.0, 4.0, "all",   1.00),
    ],
    "neo_classical": [
        (0.0, 1.0, "all",   1.00),
        (1.0, 1.0, "top",   0.85),
        (2.0, 1.0, "top",   0.85),
        (3.0, 1.0, "top",   0.80),
    ],
    "folk": [
        (0.0, 1.0, "root_5", 0.95),
        (1.0, 1.0, "top",    0.90),
        (2.0, 1.0, "root_5", 0.90),
        (3.0, 1.0, "top",    0.88),
    ],
    "bossa_nova": [
        (0.0,  0.5, "root",   0.95),
        (0.75, 1.0, "top",    0.92),
        (2.0,  0.5, "fifth",  0.85),
        (2.5,  0.5, "top",    0.92),
        (3.0,  1.0, "top",    0.90),
    ],
    "jazz_ballad": [
        (0.0, 2.0, "top3",   0.90),
        (2.0, 0.5, "top",    0.80),
        (2.5, 1.5, "top3",   0.88),
    ],
    "lo_fi": [
        (0.5, 1.5, "top",    0.85),
        (2.5, 1.5, "top",    0.82),
    ],
}

_H34 = {
    "ambient": [(0.0, 3.0, "all", 1.00)],
    "neo_classical": [
        (0.0, 1.0, "all", 1.00),
        (1.0, 1.0, "top", 0.85),
        (2.0, 1.0, "top", 0.80),
    ],
    "folk": [
        (0.0, 1.0, "root_5", 0.95),
        (1.0, 1.0, "top",    0.88),
        (2.0, 1.0, "top",    0.85),
    ],
    "bossa_nova": [
        (0.0, 1.0, "root",   0.95),
        (1.0, 1.0, "top",    0.90),
        (2.0, 1.0, "top",    0.88),
    ],
    "jazz_ballad": [(0.0, 3.0, "top3", 0.90)],
    "lo_fi": [
        (0.5, 1.0, "top", 0.85),
        (2.0, 1.0, "top", 0.80),
    ],
}

_H68 = {
    "ambient": [(0.0, 6.0, "all", 1.00)],
    "neo_classical": [
        (0.0, 1.5, "all", 1.00),
        (1.5, 1.5, "top", 0.85),
        (3.0, 1.5, "top", 0.85),
        (4.5, 1.5, "top", 0.80),
    ],
    "folk": [
        (0.0, 1.5, "root_5", 0.95),
        (1.5, 1.5, "top",    0.88),
        (3.0, 1.5, "root_5", 0.92),
        (4.5, 1.5, "top",    0.85),
    ],
    "bossa_nova": [
        (0.0, 1.5, "root", 0.95),
        (1.5, 1.5, "top",  0.90),
        (3.0, 1.5, "fifth", 0.85),
        (4.5, 1.5, "top",  0.90),
    ],
    "jazz_ballad": [
        (0.0, 3.0, "top3", 0.90),
        (3.0, 3.0, "top3", 0.88),
    ],
    "lo_fi": [
        (1.5, 1.5, "top", 0.85),
        (4.5, 1.5, "top", 0.80),
    ],
}

# ── bass per (genre, beats_per_bar) ────────────────────────────────
_B44 = {
    "ambient": [(0.0, 4.0, "root")],
    "neo_classical": [
        (0.0, 0.5, "root"),
        (0.5, 0.5, "fifth_up"),
        (1.0, 0.5, "third"),
        (1.5, 0.5, "fifth_up"),
        (2.0, 0.5, "root"),
        (2.5, 0.5, "fifth_up"),
        (3.0, 0.5, "third"),
        (3.5, 0.5, "fifth_up"),
    ],
    "folk": [
        (0.0, 1.0, "root"),
        (1.0, 1.0, "fifth"),
        (2.0, 1.0, "root"),
        (3.0, 1.0, "fifth"),
    ],
    "bossa_nova": [
        (0.0, 1.5, "root"),
        (1.5, 0.5, "fifth"),
        (2.0, 1.5, "fifth"),
        (3.5, 0.5, "root"),
    ],
    "jazz_ballad": [
        (0.0, 1.0, "root"),
        (1.0, 1.0, "third"),
        (2.0, 1.0, "fifth"),
        (3.0, 1.0, "third"),
    ],
    "lo_fi": [
        (0.0, 2.0, "root"),
        (2.0, 2.0, "fifth"),
    ],
}

_B34 = {
    "ambient": [(0.0, 3.0, "root")],
    "neo_classical": [
        (0.0, 0.5, "root"),
        (0.5, 0.5, "fifth_up"),
        (1.0, 0.5, "third"),
        (1.5, 0.5, "fifth_up"),
        (2.0, 0.5, "root"),
        (2.5, 0.5, "fifth_up"),
    ],
    "folk": [
        (0.0, 1.0, "root"),
        (1.0, 1.0, "fifth"),
        (2.0, 1.0, "fifth"),
    ],
    "bossa_nova": [
        (0.0, 1.0, "root"),
        (1.0, 1.0, "fifth"),
        (2.0, 1.0, "root"),
    ],
    "jazz_ballad": [
        (0.0, 1.0, "root"),
        (1.0, 1.0, "third"),
        (2.0, 1.0, "fifth"),
    ],
    "lo_fi": [
        (0.0, 1.5, "root"),
        (1.5, 1.5, "fifth"),
    ],
}

_B68 = {
    "ambient": [(0.0, 6.0, "root")],
    "neo_classical": [
        (0.0, 0.5, "root"),
        (0.5, 0.5, "fifth_up"),
        (1.0, 0.5, "third"),
        (1.5, 0.5, "fifth_up"),
        (3.0, 0.5, "fifth"),
        (3.5, 0.5, "fifth_up"),
        (4.0, 0.5, "third"),
        (4.5, 0.5, "fifth_up"),
    ],
    "folk": [
        (0.0, 1.5, "root"),
        (1.5, 1.5, "fifth"),
        (3.0, 1.5, "root"),
        (4.5, 1.5, "fifth"),
    ],
    "bossa_nova": [
        (0.0, 1.5, "root"),
        (3.0, 1.5, "fifth"),
        (4.5, 1.5, "root"),
    ],
    "jazz_ballad": [
        (0.0, 1.5, "root"),
        (1.5, 1.5, "third"),
        (3.0, 1.5, "fifth"),
        (4.5, 1.5, "third"),
    ],
    "lo_fi": [
        (0.0, 3.0, "root"),
        (3.0, 3.0, "fifth"),
    ],
}


def _table(beats_per_bar: int):
    if beats_per_bar == 3:
        return _H34, _B34
    if beats_per_bar == 6:
        return _H68, _B68
    return _H44, _B44


def harmony_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    h, _ = _table(bpb)
    return h.get(genre, h["ambient"])


def bass_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    _, b = _table(bpb)
    return b.get(genre, b["ambient"])


# ── voice subset helpers ───────────────────────────────────────────
def chord_subset(chord_pitches, kind: str):
    if not chord_pitches:
        return []
    cp = list(chord_pitches)
    if kind == "all":
        return cp
    if kind == "top":
        return cp[1:]
    if kind == "top3":
        return cp[1:4] if len(cp) > 1 else cp
    if kind == "root":
        return [cp[0]]
    if kind == "fifth":
        return [cp[2]] if len(cp) > 2 else [cp[0]]
    if kind == "root_5":
        return [cp[0], cp[2]] if len(cp) > 2 else [cp[0]]
    return cp


# ── bass pitch resolution ──────────────────────────────────────────
def bass_pitch(degree_to_midi_fn, key, mode, chord_root, kind: str) -> int:
    if kind == "root":
        return degree_to_midi_fn(key, mode, chord_root,
                                 octave_shift=-1, base_octave=2)
    if kind == "fifth":
        return degree_to_midi_fn(key, mode, chord_root + 4,
                                 octave_shift=-1, base_octave=2)
    if kind == "third":
        return degree_to_midi_fn(key, mode, chord_root + 2,
                                 octave_shift=-1, base_octave=2)
    if kind == "fifth_up":
        return degree_to_midi_fn(key, mode, chord_root + 4,
                                 octave_shift=0,  base_octave=3)
    return degree_to_midi_fn(key, mode, chord_root,
                             octave_shift=-1, base_octave=2)


# ── percussion patterns ────────────────────────────────────────────
#
# Each event: (start_beat, kind, vel_mult). `kind` is one of:
#   "tap"     — soft wood click (metronome-ish)
#   "shaker"  — short white-noise burst
#   "brush"   — pink-noise brush sweep
#   "ride"    — metallic bell ping
#   "kick"    — low membrane thump
#   "snare"   — mid white-noise crack
#   "hat"     — high metallic tick
#
# These are tuned for "박자감 without drums" — the percussive layer is
# always under the harmony comping in volume.

_P44 = {
    "ambient":      [],
    "neo_classical": [
        (0.0, "tap",    0.55),
        (2.0, "tap",    0.45),
    ],
    "folk": [
        (0.0, "tap",    0.50),
        (1.0, "brush",  0.65),    # backbeat
        (2.0, "tap",    0.45),
        (3.0, "brush",  0.65),
    ],
    "bossa_nova": [
        (0.0, "shaker", 0.55),
        (0.5, "shaker", 0.40),
        (1.0, "shaker", 0.55),
        (1.5, "shaker", 0.40),
        (2.0, "shaker", 0.55),
        (2.5, "shaker", 0.40),
        (3.0, "shaker", 0.55),
        (3.5, "shaker", 0.40),
    ],
    "jazz_ballad": [
        (0.0, "ride",   0.40),
        (1.0, "brush",  0.55),    # backbeat
        (1.5, "ride",   0.30),
        (2.0, "ride",   0.40),
        (2.5, "ride",   0.30),
        (3.0, "brush",  0.55),
        (3.5, "ride",   0.30),
    ],
    "lo_fi": [
        (0.0, "kick",   0.75),
        (0.5, "hat",    0.30),
        (1.0, "hat",    0.30),
        (1.5, "hat",    0.30),
        (2.0, "snare",  0.65),
        (2.5, "hat",    0.30),
        (3.0, "hat",    0.30),
        (3.5, "hat",    0.30),
    ],
}

_P34 = {
    "ambient":      [],
    "neo_classical": [(0.0, "tap", 0.55)],
    "folk": [
        (0.0, "tap",    0.55),    # waltz down-beat
        (1.0, "brush",  0.55),
        (2.0, "brush",  0.55),
    ],
    "bossa_nova": [
        (0.0, "shaker", 0.55),
        (0.5, "shaker", 0.40),
        (1.0, "shaker", 0.50),
        (1.5, "shaker", 0.40),
        (2.0, "shaker", 0.50),
        (2.5, "shaker", 0.40),
    ],
    "jazz_ballad": [
        (0.0, "ride",   0.40),
        (1.0, "brush",  0.55),
        (2.0, "ride",   0.40),
    ],
    "lo_fi": [
        (0.0, "kick",   0.70),
        (1.0, "snare",  0.55),
        (2.0, "snare",  0.55),
    ],
}

_P68 = {
    "ambient":      [],
    "neo_classical": [
        (0.0, "tap",    0.55),
        (3.0, "tap",    0.45),
    ],
    "folk": [
        (0.0, "tap",    0.55),
        (3.0, "brush",  0.60),
    ],
    "bossa_nova": [
        (0.0, "shaker", 0.55),
        (1.0, "shaker", 0.40),
        (2.0, "shaker", 0.40),
        (3.0, "shaker", 0.55),
        (4.0, "shaker", 0.40),
        (5.0, "shaker", 0.40),
    ],
    "jazz_ballad": [
        (0.0, "ride",   0.40),
        (3.0, "ride",   0.40),
        (1.5, "brush",  0.45),
        (4.5, "brush",  0.45),
    ],
    "lo_fi": [
        (0.0, "kick",   0.70),
        (3.0, "snare",  0.55),
    ],
}


def percussion_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    table = {3: _P34, 4: _P44, 6: _P68}.get(bpb, _P44)
    return table.get(genre, [])


# General MIDI drum notes (channel 9). Used by render.py to give the
# downloaded MIDI a sensible drum kit when opened in a DAW.
GM_DRUM_NOTE = {
    "tap":    75,   # claves
    "shaker": 70,
    "brush":  39,   # hand clap (closest soft attack)
    "ride":   51,
    "kick":   36,
    "snare":  38,
    "hat":    42,
}
