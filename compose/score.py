"""IR -> ABC notation -> SVG via verovio.

We convert the melody track only (single-staff lead sheet) to keep the
score readable. Harmony is annotated as chord symbols above the staff.

ABC reference: https://abcnotation.com/wiki/abc:standard:v2.1
"""

from __future__ import annotations

import verovio  # type: ignore

from .scales import MODE_INTERVALS

# pitch class -> ABC pitch letter (lowercase = octave above middle C)
_PC_TO_LETTER = {
    0:  ("C", 0),  1:  ("C", 0),  # use C# via accidental
    2:  ("D", 0),  3:  ("D", 0),
    4:  ("E", 0),  5:  ("F", 0),
    6:  ("F", 0),  7:  ("G", 0),
    8:  ("G", 0),  9:  ("A", 0),
    10: ("A", 0),  11: ("B", 0),
}
_SHARP_PCS = {1, 3, 6, 8, 10}
_NATURAL_LETTER = {0: "C", 2: "D", 4: "E", 5: "F", 7: "G", 9: "A", 11: "B"}
_SHARP_LETTER   = {1: "C", 3: "D", 6: "F", 8: "G", 10: "A"}

ABC_KEY_MAP = {
    "ionian":     "",      # major
    "dorian":     "dor",
    "lydian":     "lyd",
    "mixolydian": "mix",
    "aeolian":    "m",     # natural minor — K:Am etc.
}

# Pitch class → letter for chord symbol roots. We only use diatonic
# keys (C/D/E/F/G/A/B) so the roots are almost always natural; sharps
# only appear on borrowed degrees, which we accept rather than try to
# pick the "correct" enharmonic spelling per key.
_PC_TO_CHORD_LETTER = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
]


def _chord_symbol(key_root: str, mode: str, degree: int,
                  with_seventh: bool = False) -> str:
    """Build a lead-sheet chord symbol from a scale degree.

    Quality (maj/min/dim/aug) is derived from the actual mode-diatonic
    stacking via `chord_pitches`, so it follows whatever the composer
    actually plays (e.g. III in dorian = major, III in ionian = minor).
    """
    from .scales import PITCH_CLASS, chord_pitches
    pitches = chord_pitches(key_root, mode, degree, voicing="triad")
    root, third, fifth = pitches[0], pitches[1], pitches[2]
    third_int = (third - root) % 12
    fifth_int = (fifth - root) % 12

    letter = _PC_TO_CHORD_LETTER[root % 12]
    if third_int == 3 and fifth_int == 6:
        quality = "dim"
    elif third_int == 4 and fifth_int == 8:
        quality = "aug"
    elif third_int == 3:
        quality = "m"
    else:
        quality = ""        # major triad
    sym = letter + quality
    if with_seventh:
        # Determine 7th quality: maj7 (11), dom7 (10), m7b5 (10 over dim), etc.
        # We keep it simple: just append "7" — readers will infer maj7 in
        # ionian/lydian/mixolydian context. Skipping for now to keep the
        # lead-sheet uncluttered.
        sym += "7"
    return sym


def _midi_to_abc(midi: int, key_sharps: set[int]) -> str:
    """Render a MIDI note as an ABC pitch token (no length).

    `key_sharps` are pitch classes already in the key signature; we only
    emit accidentals when a note is *not* in the key.
    """
    pc = midi % 12
    octave = midi // 12 - 1   # MIDI 60 -> C4

    if pc in _NATURAL_LETTER:
        letter = _NATURAL_LETTER[pc]
        accidental = ""
    else:
        letter = _SHARP_LETTER[pc]
        accidental = "^" if pc not in key_sharps else ""

    # ABC convention: C..B = octave 4. For octave 5: c..b. Octave 6: c'..
    # Octave 3: C,..B,. Octave 2: C,, etc.
    if octave >= 5:
        body = letter.lower()
        body += "'" * (octave - 5)
    else:
        body = letter.upper()
        body += "," * (4 - octave)

    return accidental + body


def _key_sharps(key_root: str, mode: str) -> set[int]:
    from .scales import PITCH_CLASS
    intervals = MODE_INTERVALS[mode]
    tonic = PITCH_CLASS[key_root]
    return {(tonic + i) % 12 for i in intervals}


def _abc_duration(beats: float, unit: float) -> str:
    """ABC length token. unit = the L: header (1/4 or 1/8 etc).
    A quarter-note in L:1/4 is "1" or "" (default). A half-note is "2".
    A dotted-quarter in L:1/8 is "3" (3 eighths). Etc."""
    n_units = beats / unit
    # round to nearest 0.5 unit
    n_units = round(n_units * 2) / 2
    if n_units < 0.5:
        n_units = 0.5
    if n_units == int(n_units):
        n = int(n_units)
        return "" if n == 1 else str(n)
    # half-unit case: "/2" ; "3/2" etc
    num = int(round(n_units * 2))
    return f"{num}/2"


def ir_to_abc(ir: dict, *, title_suffix: str = "") -> str:
    spec = ir["spec"]
    meta = ir["meta"]
    key_root = spec["key_root"]
    mode = spec["mode"]
    bpm = spec["bpm"]
    meter = spec["meter"]
    bpb = float(meter.split("/")[0])
    key_sharps = _key_sharps(key_root, mode)

    # ABC default note length: eighth-note (L:1/8) gives reasonable
    # readability for our 0.5-2 beat events.
    unit_beats = 0.5
    abc_key = key_root + ABC_KEY_MAP[mode]

    title = f"busy day  {meta['date']}"
    if title_suffix:
        title += f"  ({title_suffix})"

    lines = [
        "X:1",
        f"T:{title}",
        f"M:{meter}",
        "L:1/8",
        f"Q:1/4={bpm}",
        f"K:{abc_key}",
    ]

    # Group melody events by bar
    bars: dict[int, list[dict]] = {}
    for ev in ir["tracks"]["melody"]:
        bars.setdefault(ev["bar"], []).append(ev)

    # Pre-compute chord symbol per bar from ir["bars"] (lead-sheet style:
    # only emit at chord change so the score stays clean).
    bar_meta = ir.get("bars") or []
    chord_at_bar: dict[int, str] = {}
    prev_sym = None
    for idx, meta in enumerate(bar_meta):
        deg = meta.get("chord_degree")
        if deg is None:
            continue
        sym = _chord_symbol(key_root, mode, int(deg))
        if sym != prev_sym:
            chord_at_bar[idx] = sym
            prev_sym = sym

    n_bars = ir["total_bars"]
    line_items: list[str] = []
    bars_per_line = 4

    for b in range(n_bars):
        events = sorted(bars.get(b, []), key=lambda e: e["start_beat"])
        chord_prefix = f'"{chord_at_bar[b]}"' if b in chord_at_bar else ""
        if not events:
            # whole-bar rest; ABC: "z<dur>"
            rest = _abc_duration(bpb, unit_beats) or "1"
            content = chord_prefix + "z" + rest
        else:
            tokens = []
            cursor = 0.0
            for i, ev in enumerate(events):
                gap = ev["start_beat"] - cursor
                if gap > 0.05:
                    # Chord symbol attaches to the first token of the bar
                    # (rest or note — both accept a "Cmaj" prefix in ABC).
                    rest_tok = "z" + _abc_duration(gap, unit_beats)
                    if i == 0 and chord_prefix:
                        tokens.append(chord_prefix + rest_tok)
                    else:
                        tokens.append(rest_tok)
                pitch_tok = _midi_to_abc(ev["pitch"], key_sharps)
                dur_tok   = _abc_duration(ev["dur_beats"], unit_beats)
                full = pitch_tok + dur_tok
                if i == 0 and chord_prefix and not (gap > 0.05):
                    full = chord_prefix + full
                tokens.append(full)
                cursor = ev["start_beat"] + ev["dur_beats"]
            # pad out to end of bar
            tail = bpb - cursor
            if tail > 0.05:
                tokens.append("z" + _abc_duration(tail, unit_beats))
            content = " ".join(tokens)
        line_items.append(content)

    # Stitch bars into 4-per-line measures with bar lines
    output_lines = list(lines)
    for i in range(0, len(line_items), bars_per_line):
        group = line_items[i : i + bars_per_line]
        sep = " | "
        end = " |]" if (i + bars_per_line) >= len(line_items) else " |"
        output_lines.append(sep.join(group) + end)

    return "\n".join(output_lines) + "\n"


_TOOLKIT: verovio.toolkit | None = None


def _toolkit() -> verovio.toolkit:
    global _TOOLKIT
    if _TOOLKIT is None:
        tk = verovio.toolkit()
        tk.setOptions({
            "pageWidth":  2100,
            "pageHeight": 800,
            "scale":      45,
            "footer":     "none",
            "header":     "encoded",
            "adjustPageHeight": True,
            "spacingNonLinear": 0.6,
            "spacingLinear":    0.25,
        })
        _TOOLKIT = tk
    return _TOOLKIT


def render_svg(ir: dict, *, title_suffix: str = "") -> str:
    abc = ir_to_abc(ir, title_suffix=title_suffix)
    tk = _toolkit()
    tk.loadData(abc)
    return tk.renderToSVG(1)
