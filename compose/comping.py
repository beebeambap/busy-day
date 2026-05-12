"""Genre-aware harmony comping + bass walking patterns.

Each *pattern* is a list of (start_beat, dur, voice_kind, vel_mult)
tuples and runs inside one bar. To break the "same rhythm 16 bars in a
row" feel, every (genre, meter) holds 1-2 patterns: a canonical cell
and an alt cell. The arranger calls `harmony_pattern_for(genre, meter,
section, rng)` once per bar and the picker biases:

    INTRO / OUTRO    → canonical (calm bookends)
    A                → 70% canonical / 30% alt
    B                → 25% canonical / 75% alt   (audibly different)
    A_PRIME          → 60% canonical / 40% alt   (back, but not identical)

Bass uses the same scheme via `bass_pattern_for`. Single-cell entries
just always return that cell. The percussion patterns below stay
single-cell on purpose — the pulse layer should be steady so the
listener can feel time even while the chord rhythm shifts.

Voice kinds (for harmony):
  "all"      — full chord (root + 3rd + 5th [+ 7th if seventh voicing])
  "top"      — 3rd + 5th [+ 7th]   (no root)
  "top3"     — top three voices
  "root"     — root only
  "fifth"    — 5th only
  "root_5"   — root + 5th

Voice kinds (for bass):
  "root"     — chord root, low octave
  "fifth"    — chord 5th, low octave
  "third"    — chord 3rd, low octave
  "fifth_up" — 5th one octave above bass register (alberti pattern)
"""

from __future__ import annotations

from random import Random


# ── harmony per (genre, beats_per_bar) ─────────────────────────────
# value = list of patterns (canonical first, alt second)

_H44 = {
    "ambient": [
        # canonical: pure pad, whole note
        [(0.0, 4.0, "all",   1.00)],
        # alt: split mid-bar into two halves so the pad "breathes"
        [(0.0, 2.0, "all",   1.00),
         (2.0, 2.0, "top",   0.85)],
    ],
    "neo_classical": [
        # canonical: block + 3 stabs
        [(0.0, 1.0, "all",   1.00),
         (1.0, 1.0, "top",   0.85),
         (2.0, 1.0, "top",   0.85),
         (3.0, 1.0, "top",   0.80)],
        # alt: longer downbeat + arpeggio tail
        [(0.0, 2.0, "all",   1.00),
         (2.0, 0.5, "top",   0.80),
         (2.5, 0.5, "fifth", 0.78),
         (3.0, 0.5, "top",   0.85),
         (3.5, 0.5, "root_5", 0.85)],
    ],
    "folk": [
        # canonical: alternating root_5 / top quarters
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 1.0, "top",    0.90),
         (2.0, 1.0, "root_5", 0.90),
         (3.0, 1.0, "top",    0.88)],
        # alt: same shell, eighth-note answer on beats 2 & 4
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 0.5, "top",    0.88),
         (1.5, 0.5, "top",    0.82),
         (2.0, 1.0, "root_5", 0.92),
         (3.0, 0.5, "top",    0.88),
         (3.5, 0.5, "top",    0.82)],
    ],
    "bossa_nova": [
        # canonical: bossa rhythm
        [(0.0,  0.5, "root",   0.95),
         (0.75, 1.0, "top",    0.92),
         (2.0,  0.5, "fifth",  0.85),
         (2.5,  0.5, "top",    0.92),
         (3.0,  1.0, "top",    0.90)],
        # alt: anticipated comp
        [(0.0,  0.75, "root",  0.95),
         (0.75, 1.25, "top",   0.92),
         (2.5,  0.5, "fifth",  0.88),
         (3.0,  0.5, "top",    0.90),
         (3.5,  0.5, "top",    0.85)],
    ],
    "jazz_ballad": [
        # canonical: long stabs
        [(0.0, 2.0, "top3",   0.90),
         (2.0, 0.5, "top",    0.80),
         (2.5, 1.5, "top3",   0.88)],
        # alt: 4 stabs, busier
        [(0.0, 1.0, "top3",   0.90),
         (1.5, 0.5, "top",    0.80),
         (2.0, 1.0, "top3",   0.85),
         (3.5, 0.5, "top",    0.82)],
    ],
    "lo_fi": [
        # canonical: lazy 2-hit
        [(0.5, 1.5, "top",    0.85),
         (2.5, 1.5, "top",    0.82)],
        # alt: 3 hits with anticipation
        [(0.5, 1.0, "top",    0.85),
         (1.75, 0.75, "top",  0.80),
         (2.5, 1.5, "top",    0.82)],
    ],
}

_H34 = {
    "ambient": [
        [(0.0, 3.0, "all", 1.00)],
        [(0.0, 1.5, "all", 1.00),
         (1.5, 1.5, "top", 0.85)],
    ],
    "neo_classical": [
        [(0.0, 1.0, "all", 1.00),
         (1.0, 1.0, "top", 0.85),
         (2.0, 1.0, "top", 0.80)],
        [(0.0, 1.5, "all", 1.00),
         (1.5, 0.5, "top", 0.85),
         (2.0, 0.5, "fifth", 0.80),
         (2.5, 0.5, "top",  0.85)],
    ],
    "folk": [
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 1.0, "top",    0.88),
         (2.0, 1.0, "top",    0.85)],
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 0.5, "top",    0.88),
         (1.5, 0.5, "top",    0.82),
         (2.0, 1.0, "top",    0.85)],
    ],
    "bossa_nova": [
        [(0.0, 1.0, "root",   0.95),
         (1.0, 1.0, "top",    0.90),
         (2.0, 1.0, "top",    0.88)],
        [(0.0, 0.5, "root",   0.95),
         (0.75, 1.25, "top",  0.90),
         (2.0, 1.0, "top",    0.88)],
    ],
    "jazz_ballad": [
        [(0.0, 3.0, "top3", 0.90)],
        [(0.0, 1.5, "top3", 0.90),
         (1.5, 1.5, "top",  0.85)],
    ],
    "lo_fi": [
        [(0.5, 1.0, "top", 0.85),
         (2.0, 1.0, "top", 0.80)],
        [(0.0, 1.0, "top", 0.85),
         (1.5, 1.5, "top", 0.82)],
    ],
}

_H68 = {
    "ambient": [
        [(0.0, 6.0, "all", 1.00)],
        [(0.0, 3.0, "all", 1.00),
         (3.0, 3.0, "top", 0.85)],
    ],
    "neo_classical": [
        [(0.0, 1.5, "all", 1.00),
         (1.5, 1.5, "top", 0.85),
         (3.0, 1.5, "top", 0.85),
         (4.5, 1.5, "top", 0.80)],
        [(0.0, 3.0, "all", 1.00),
         (3.0, 1.0, "top",   0.85),
         (4.0, 1.0, "fifth", 0.80),
         (5.0, 1.0, "top",   0.85)],
    ],
    "folk": [
        [(0.0, 1.5, "root_5", 0.95),
         (1.5, 1.5, "top",    0.88),
         (3.0, 1.5, "root_5", 0.92),
         (4.5, 1.5, "top",    0.85)],
        [(0.0, 1.5, "root_5", 0.95),
         (1.5, 0.75, "top",   0.88),
         (2.25, 0.75, "top",  0.80),
         (3.0, 1.5, "root_5", 0.92),
         (4.5, 1.5, "top",    0.85)],
    ],
    "bossa_nova": [
        [(0.0, 1.5, "root",  0.95),
         (1.5, 1.5, "top",   0.90),
         (3.0, 1.5, "fifth", 0.85),
         (4.5, 1.5, "top",   0.90)],
        [(0.0, 0.75, "root", 0.95),
         (0.75, 2.25, "top", 0.90),
         (3.0, 0.75, "fifth", 0.85),
         (3.75, 2.25, "top", 0.88)],
    ],
    "jazz_ballad": [
        [(0.0, 3.0, "top3", 0.90),
         (3.0, 3.0, "top3", 0.88)],
        [(0.0, 1.5, "top3", 0.90),
         (1.5, 1.5, "top",  0.82),
         (3.0, 3.0, "top3", 0.88)],
    ],
    "lo_fi": [
        [(1.5, 1.5, "top", 0.85),
         (4.5, 1.5, "top", 0.80)],
        [(0.0, 1.0, "top", 0.85),
         (3.0, 1.5, "top", 0.82)],
    ],
}

# ── bass per (genre, beats_per_bar) ────────────────────────────────
_B44 = {
    "ambient": [
        [(0.0, 4.0, "root")],
        [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],
    ],
    "neo_classical": [
        # canonical: alberti
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth_up"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth_up"),
         (2.0, 0.5, "root"),
         (2.5, 0.5, "fifth_up"),
         (3.0, 0.5, "third"),
         (3.5, 0.5, "fifth_up")],
        # alt: walking quarters
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
    ],
    "folk": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "root"),
         (3.0, 1.0, "fifth")],
        # alt: walking 1-5-3-↑5 (third + upper fifth = scale movement)
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "third"),
         (3.0, 1.0, "fifth_up")],
    ],
    "bossa_nova": [
        [(0.0, 1.5, "root"),
         (1.5, 0.5, "fifth"),
         (2.0, 1.5, "fifth"),
         (3.5, 0.5, "root")],
        # alt: 1-3-5-↑5 with anticipation
        [(0.0, 1.5, "root"),
         (1.5, 0.5, "third"),
         (2.0, 1.5, "fifth"),
         (3.5, 0.5, "fifth_up")],
    ],
    "jazz_ballad": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
        # alt: chromatic-feeling fifth_up between
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth_up"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
    ],
    "lo_fi": [
        [(0.0, 2.0, "root"),
         (2.0, 2.0, "fifth")],
        # alt: 1-3-5-3 walking
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
    ],
}

_B34 = {
    "ambient": [
        [(0.0, 3.0, "root")],
        [(0.0, 1.5, "root"), (1.5, 1.5, "fifth")],
    ],
    "neo_classical": [
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth_up"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth_up"),
         (2.0, 0.5, "root"),
         (2.5, 0.5, "fifth_up")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth")],
    ],
    "folk": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "fifth")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth")],
    ],
    "bossa_nova": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "root")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth")],
    ],
    "jazz_ballad": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "third")],
    ],
    "lo_fi": [
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "root")],
    ],
}

_B68 = {
    "ambient": [
        [(0.0, 6.0, "root")],
        [(0.0, 3.0, "root"), (3.0, 3.0, "fifth")],
    ],
    "neo_classical": [
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth_up"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth_up"),
         (3.0, 0.5, "fifth"),
         (3.5, 0.5, "fifth_up"),
         (4.0, 0.5, "third"),
         (4.5, 0.5, "fifth_up")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "third"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "third")],
    ],
    "folk": [
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 1.5, "fifth")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 1.5, "third")],
    ],
    "bossa_nova": [
        [(0.0, 1.5, "root"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "root")],
        [(0.0, 3.0, "root"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "fifth")],
    ],
    "jazz_ballad": [
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "third"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "third")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "third"),
         (4.5, 1.5, "fifth")],
    ],
    "lo_fi": [
        [(0.0, 3.0, "root"),
         (3.0, 3.0, "fifth")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 1.5, "fifth")],
    ],
}


def _table(beats_per_bar: int):
    if beats_per_bar == 3:
        return _H34, _B34
    if beats_per_bar == 6:
        return _H68, _B68
    return _H44, _B44


# ── section-aware probability of choosing the alt cell ────────────
_ALT_BIAS = {
    "INTRO":   0.00,
    "A":       0.30,
    "B":       0.75,
    "A_PRIME": 0.40,
    "OUTRO":   0.00,
}


def _pick_cell(cells, section, rng: Random):
    """Pick canonical or alt cell based on section bias."""
    if not cells:
        return []
    if len(cells) == 1:
        return cells[0]
    p_alt = _ALT_BIAS.get(section, 0.30)
    return cells[1] if rng.random() < p_alt else cells[0]


def _maybe_drop_last(events, rng: Random, p: float = 0.12):
    """Tiny breath: occasionally drop the trailing event of a 3+ event
    pattern so the bar feels more spoken than typed."""
    if len(events) >= 3 and rng.random() < p:
        return events[:-1]
    return events


def harmony_pattern_for(genre: str, meter: str,
                        section: str, rng: Random):
    bpb = int(meter.split("/")[0])
    h, _ = _table(bpb)
    cells = h.get(genre, h["ambient"])
    return _maybe_drop_last(_pick_cell(cells, section, rng), rng)


def bass_pattern_for(genre: str, meter: str,
                     section: str, rng: Random):
    bpb = int(meter.split("/")[0])
    _, b = _table(bpb)
    cells = b.get(genre, b["ambient"])
    return _maybe_drop_last(_pick_cell(cells, section, rng), rng, p=0.08)


# Backward-compat: callers without rng/section get the canonical cell.
def harmony_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    h, _ = _table(bpb)
    cells = h.get(genre, h["ambient"])
    return cells[0] if cells else []


def bass_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    _, b = _table(bpb)
    cells = b.get(genre, b["ambient"])
    return cells[0] if cells else []


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
# Same canonical/alt list-of-cells shape as harmony/bass so the picker
# logic can mirror them. Alt cells are deliberately close to canonical
# (one or two voice swaps, not a different beat) so the pulse stays
# steady while the texture varies.

_P44 = {
    "ambient":      [
        [],
        [],
    ],
    "neo_classical": [
        [(0.0, "tap", 0.55), (2.0, "tap", 0.45)],
        [(0.0, "tap", 0.55), (1.5, "brush", 0.40), (2.0, "tap", 0.45)],
    ],
    "folk": [
        [(0.0, "tap", 0.50), (1.0, "brush", 0.65),
         (2.0, "tap", 0.45), (3.0, "brush", 0.65)],
        # alt: double-brush on 2 & 4 for emphasis
        [(0.0, "tap", 0.50),
         (1.0, "brush", 0.65), (1.5, "brush", 0.45),
         (2.0, "tap", 0.45),
         (3.0, "brush", 0.65), (3.5, "brush", 0.45)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
         (1.0, "shaker", 0.55), (1.5, "shaker", 0.40),
         (2.0, "shaker", 0.55), (2.5, "shaker", 0.40),
         (3.0, "shaker", 0.55), (3.5, "shaker", 0.40)],
        # alt: tap on 1 + 3, lighter shaker between
        [(0.0, "tap",    0.55),
         (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
         (1.5, "shaker", 0.35),
         (2.0, "tap",    0.50),
         (2.5, "shaker", 0.35), (3.0, "shaker", 0.45),
         (3.5, "shaker", 0.35)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (1.0, "brush", 0.55),
         (1.5, "ride", 0.30), (2.0, "ride", 0.40),
         (2.5, "ride", 0.30), (3.0, "brush", 0.55),
         (3.5, "ride", 0.30)],
        # alt: brushes only — softer chorus-like feel
        [(0.0, "brush", 0.45), (1.0, "brush", 0.55),
         (2.0, "brush", 0.45), (3.0, "brush", 0.55)],
    ],
    "lo_fi": [
        [(0.0, "kick",  0.75),
         (0.5, "hat",   0.30), (1.0, "hat", 0.30), (1.5, "hat", 0.30),
         (2.0, "snare", 0.65),
         (2.5, "hat",   0.30), (3.0, "hat", 0.30), (3.5, "hat", 0.30)],
        # alt: kick on 1+2.5 (syncopated), snare 3
        [(0.0, "kick",  0.75),
         (0.5, "hat",   0.30), (1.0, "hat", 0.30), (1.5, "hat", 0.30),
         (2.0, "snare", 0.60),
         (2.5, "kick",  0.55), (3.0, "hat", 0.30), (3.5, "hat", 0.30)],
    ],
}

_P34 = {
    "ambient":      [[], []],
    "neo_classical": [
        [(0.0, "tap", 0.55)],
        [(0.0, "tap", 0.55), (2.0, "tap", 0.40)],
    ],
    "folk": [
        [(0.0, "tap", 0.55), (1.0, "brush", 0.55), (2.0, "brush", 0.55)],
        [(0.0, "tap", 0.55), (1.0, "brush", 0.55),
         (1.5, "brush", 0.40), (2.0, "brush", 0.55)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
         (1.0, "shaker", 0.50), (1.5, "shaker", 0.40),
         (2.0, "shaker", 0.50), (2.5, "shaker", 0.40)],
        [(0.0, "tap",    0.50),
         (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
         (1.5, "shaker", 0.35), (2.0, "shaker", 0.45),
         (2.5, "shaker", 0.35)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (1.0, "brush", 0.55), (2.0, "ride", 0.40)],
        [(0.0, "brush", 0.45), (1.0, "brush", 0.55), (2.0, "brush", 0.45)],
    ],
    "lo_fi": [
        [(0.0, "kick", 0.70), (1.0, "snare", 0.55), (2.0, "snare", 0.55)],
        [(0.0, "kick", 0.70), (1.5, "snare", 0.55),
         (2.0, "hat", 0.30), (2.5, "hat", 0.30)],
    ],
}

_P68 = {
    "ambient":      [[], []],
    "neo_classical": [
        [(0.0, "tap", 0.55), (3.0, "tap", 0.45)],
        [(0.0, "tap", 0.55), (3.0, "brush", 0.40)],
    ],
    "folk": [
        [(0.0, "tap", 0.55), (3.0, "brush", 0.60)],
        [(0.0, "tap", 0.55), (1.5, "brush", 0.40),
         (3.0, "brush", 0.60), (4.5, "brush", 0.40)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (1.0, "shaker", 0.40),
         (2.0, "shaker", 0.40), (3.0, "shaker", 0.55),
         (4.0, "shaker", 0.40), (5.0, "shaker", 0.40)],
        [(0.0, "tap",    0.50),
         (1.0, "shaker", 0.35), (2.0, "shaker", 0.35),
         (3.0, "tap",    0.50),
         (4.0, "shaker", 0.35), (5.0, "shaker", 0.35)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (3.0, "ride", 0.40),
         (1.5, "brush", 0.45), (4.5, "brush", 0.45)],
        [(0.0, "brush", 0.45), (3.0, "brush", 0.55)],
    ],
    "lo_fi": [
        [(0.0, "kick", 0.70), (3.0, "snare", 0.55)],
        [(0.0, "kick", 0.70), (1.5, "hat", 0.30),
         (3.0, "snare", 0.55), (4.5, "hat", 0.30)],
    ],
}


def percussion_pattern_for(genre: str, meter: str,
                           section: str, rng: Random):
    bpb = int(meter.split("/")[0])
    table = {3: _P34, 4: _P44, 6: _P68}.get(bpb, _P44)
    cells = table.get(genre, [[]])
    return _pick_cell(cells, section, rng)


# Backward-compatible: no-rng helper returns the canonical cell.
def percussion_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    table = {3: _P34, 4: _P44, 6: _P68}.get(bpb, _P44)
    cells = table.get(genre, [])
    return cells[0] if cells else []


# General MIDI drum notes (channel 9). Used by render.py to give the
# downloaded MIDI a sensible drum kit when opened in a DAW.
GM_DRUM_NOTE = {
    "tap":    75,
    "shaker": 70,
    "brush":  39,
    "ride":   51,
    "kick":   36,
    "snare":  38,
    "hat":    42,
}
