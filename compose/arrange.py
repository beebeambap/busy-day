"""Form assembly: glue progressions, melodies, bass, pad into one IR.

IR (intermediate representation) shape:
{
  "meta": { date, city_id, seed, generator_ver, ... },
  "spec": { key_root, mode, genre, bpm, meter, motif_id, ... },
  "form": [ "INTRO", "A", "B", "A_PRIME", "OUTRO" ],
  "tracks": {
    "melody": [ {bar, start_beat, pitch, dur_beats, vel}, ... ],
    "harmony": [ {bar, start_beat, pitches: [...], dur_beats, vel}, ... ],
    "bass":    [ {bar, start_beat, pitch, dur_beats, vel}, ... ]
  },
  "bars": [ {section, chord_degree, beats}, ... ]
}
"""

from __future__ import annotations

import hashlib
import json
from random import Random

from . import GENERATOR_VER
from .features import Features
from .harmony import progression, voicing_for_genre
from .melody import melody_over_progression
from .scales import chord_pitches, degree_to_midi


def _section_lengths(genre: str, bpm: int, bpb: float,
                     target_sec: float = 62.0) -> dict[str, int]:
    """Distribute ~target_sec of total music across the 5 sections."""
    target_bars = max(8, round(target_sec * bpm / 60.0 / bpb))

    # base proportions sum to 1.0
    prop = {"INTRO": 0.10, "A": 0.35, "B": 0.25, "A_PRIME": 0.22, "OUTRO": 0.08}
    if genre == "ambient":
        prop = {"INTRO": 0.18, "A": 0.30, "B": 0.20, "A_PRIME": 0.20, "OUTRO": 0.12}
    if genre == "lo_fi":
        prop = {"INTRO": 0.08, "A": 0.42, "B": 0.18, "A_PRIME": 0.24, "OUTRO": 0.08}

    raw = {k: max(1, round(target_bars * v)) for k, v in prop.items()}
    # reconcile rounding so the sum equals target_bars exactly
    diff = target_bars - sum(raw.values())
    if diff != 0:
        raw["A"] = max(1, raw["A"] + diff)
    return raw


def _beats_per_bar(meter: str) -> float:
    n, d = meter.split("/")
    return float(n)


def _pitch_class_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = midi // 12 - 1
    return f"{names[midi % 12]}{octave}"


def compose_ir(
    *,
    date_iso: str,
    city_id: str,
    seed: int,
    rng: Random,
    features: Features,
    spec: dict,
) -> dict:
    bpm = spec["bpm"]
    mode = spec["mode"]
    key = spec["key_root"]
    genre = spec["genre"]
    meter = spec["meter"]
    motif = spec["motif"]
    bpb = _beats_per_bar(meter)

    sec_len = _section_lengths(genre, bpm, bpb)
    form = ["INTRO", "A", "B", "A_PRIME", "OUTRO"]
    total_bars = sum(sec_len[s] for s in form)

    # Build a single progression that spans all non-intro/outro sections,
    # with intro/outro pinned around tonic for stability.
    chord_seq: list[int] = []
    bars_meta: list[dict] = []

    for section in form:
        n = sec_len[section]
        if section in ("INTRO", "OUTRO"):
            seq = [1] * n
            if section == "OUTRO" and n >= 2:
                seq[-2] = 4 if mode != "mixolydian" else 7
        else:
            cad = "tonic" if section == "A_PRIME" else "open"
            seq = progression(rng, mode, n, cadence=cad)
        chord_seq.extend(seq)
        for d in seq:
            bars_meta.append({"section": section, "chord_degree": d, "beats": bpb})

    # melody over the whole sequence (intro/outro included; intro often sparse)
    melody_bars = melody_over_progression(rng, motif, chord_seq, bpb)

    voicing = voicing_for_genre(genre)
    melody_events = []
    harmony_events = []
    bass_events = []

    cur_bar = 0
    for bar_idx, (chord_root, mel_notes, meta) in enumerate(
        zip(chord_seq, melody_bars, bars_meta)
    ):
        section = meta["section"]
        # ── melody (skip in INTRO half the time, sparse in OUTRO) ─────
        play_melody = True
        if section == "INTRO" and bar_idx == 0:
            play_melody = False
        if section == "OUTRO" and bar_idx == len(chord_seq) - 1:
            play_melody = False

        if play_melody:
            t = 0.0
            for deg, oct_shift, dur in mel_notes:
                pitch = degree_to_midi(key, mode, deg, octave_shift=oct_shift,
                                       base_octave=5)
                if 36 <= pitch <= 96:
                    melody_events.append({
                        "bar": cur_bar,
                        "start_beat": round(t, 4),
                        "pitch": pitch,
                        "dur_beats": round(dur, 4),
                        "vel": 70 + int(rng.uniform(-6, 6)),
                    })
                t += dur

        # ── harmony (pad chord) ──────────────────────────────────────
        pitches = chord_pitches(key, mode, chord_root, voicing=voicing,
                                base_octave=3)
        harmony_events.append({
            "bar": cur_bar,
            "start_beat": 0.0,
            "pitches": pitches,
            "dur_beats": bpb,
            "vel": 50 + int(rng.uniform(-4, 4)),
        })

        # ── bass: root-pedal, with a 5th passing on beat 3 in 4/4 ────
        bass_root = degree_to_midi(key, mode, chord_root, octave_shift=-1,
                                   base_octave=2)
        bass_events.append({
            "bar": cur_bar, "start_beat": 0.0,
            "pitch": bass_root, "dur_beats": bpb / 2, "vel": 60,
        })
        if bpb >= 4:
            fifth = degree_to_midi(key, mode, chord_root + 4,
                                   octave_shift=-1, base_octave=2)
            bass_events.append({
                "bar": cur_bar, "start_beat": bpb / 2,
                "pitch": fifth, "dur_beats": bpb / 2, "vel": 58,
            })

        cur_bar += 1

    # signature & start_pitch for anti-repetition memory
    sig_input = (
        ",".join(str(d) for d in chord_seq)
        + f"|{motif['id']}|{key}|{genre}|{mode}"
    )
    signature = hashlib.sha1(sig_input.encode()).hexdigest()[:16]

    start_pitch_midi = (
        melody_events[0]["pitch"] if melody_events
        else degree_to_midi(key, mode, 1, base_octave=5)
    )

    duration_beats = total_bars * bpb
    duration_sec = duration_beats * 60.0 / bpm

    return {
        "meta": {
            "date": date_iso,
            "city_id": city_id,
            "seed": seed,
            "generator_ver": GENERATOR_VER,
        },
        "spec": {
            "key_root": key,
            "mode": mode,
            "genre": genre,
            "bpm": bpm,
            "meter": meter,
            "motif_id": motif["id"],
            "voicing": voicing,
        },
        "features": features.as_dict(),
        "form": form,
        "section_bars": sec_len,
        "bars": bars_meta,
        "tracks": {
            "melody":  melody_events,
            "harmony": harmony_events,
            "bass":    bass_events,
        },
        "signature": signature,
        "start_pitch": _pitch_class_name(start_pitch_midi),
        "duration_short_sec": int(round(duration_sec)),
        "duration_long_sec": int(round(duration_sec * 2.2)),
        "total_bars": total_bars,
    }


def write_ir(ir: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ir, fh, ensure_ascii=False, indent=2)
