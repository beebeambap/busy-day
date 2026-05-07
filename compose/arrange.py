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
from .comping import (
    bass_pattern,
    bass_pitch as _bass_pitch,
    chord_subset,
    harmony_pattern,
    percussion_pattern,
)
from .features import Features
from .harmony import progression, voicing_for_genre
from .progressions import progression_for_intent
from .humanize import (
    apply_micro_timing,
    apply_outro_decay,
    apply_velocity_curve,
    pedal_segments,
)
from .melody import melody_over_progression
from .scales import chord_pitches, degree_to_midi


def _section_lengths(genre: str, bpm: int, bpb: float,
                     target_sec: float = 60.0) -> dict[str, int]:
    """Distribute ~target_sec of total music across the 5 sections.

    The actual rendered length lands within roughly ±5s of target_sec
    because we force a tonic OUTRO that may absorb slightly more time.
    """
    target_bars = max(8, round(target_sec * bpm / 60.0 / bpb))

    # base proportions sum to 1.0
    prop = {"INTRO": 0.10, "A": 0.35, "B": 0.25, "A_PRIME": 0.22, "OUTRO": 0.08}
    if genre == "ambient":
        prop = {"INTRO": 0.18, "A": 0.30, "B": 0.20, "A_PRIME": 0.20, "OUTRO": 0.12}
    if genre == "lo_fi":
        prop = {"INTRO": 0.08, "A": 0.42, "B": 0.18, "A_PRIME": 0.24, "OUTRO": 0.08}

    raw = {k: max(1, round(target_bars * v)) for k, v in prop.items()}
    # OUTRO needs >=2 bars so the tonic can actually breathe
    if raw["OUTRO"] < 2:
        raw["OUTRO"] = 2
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


def _apply_wind_density(bars, wind_factor, rng):
    """Modulate melody note density by wind.

    bars     : list of bars; each bar is a list of (degree, oct, dur).
    wind_factor : 0..1 (wind_mps/8 clipped).
      < 0.30  → thin: drop short interior notes, merging duration left
      > 0.60  → dense: split longer notes with a stepwise passing tone

    Mid-range (0.30..0.60) leaves the bar untouched. We deliberately
    keep the modification gentle so the Muji ceiling on density holds.
    """
    if 0.30 <= wind_factor <= 0.60:
        return bars

    out_bars = []
    if wind_factor < 0.30:
        thin_p = (0.30 - wind_factor) * 1.5  # max 0.45 at wind=0
        for bar in bars:
            new_bar = []
            for i, note in enumerate(bar):
                deg, oct_shift, dur = note
                interior = 0 < i < len(bar) - 1
                if interior and dur < 0.6 and rng.random() < thin_p and new_bar:
                    pdeg, poct, pdur = new_bar[-1]
                    new_bar[-1] = (pdeg, poct, pdur + dur)
                    continue
                new_bar.append(note)
            out_bars.append(new_bar)
        return out_bars

    # dense
    dense_p = min(1.0, (wind_factor - 0.60) * 2.0)
    for bar in bars:
        new_bar = []
        for i, note in enumerate(bar):
            deg, oct_shift, dur = note
            if dur >= 0.5 and rng.random() < dense_p:
                next_deg = bar[i + 1][0] if i + 1 < len(bar) else deg
                if next_deg == deg:
                    passing = deg + 1
                elif next_deg > deg:
                    passing = deg + 1
                else:
                    passing = deg - 1
                new_bar.append((deg, oct_shift, dur * 0.6))
                new_bar.append((passing, oct_shift, dur * 0.4))
            else:
                new_bar.append(note)
        out_bars.append(new_bar)
    return out_bars


def _spread_for(warmth: float) -> str:
    """Voicing spread from normalized warmth (0..1)."""
    if warmth < 0.30:
        return "tight"
    if warmth > 0.70:
        return "wide"
    return "default"


def compose_ir(
    *,
    date_iso: str,
    city_id: str,
    seed: int,
    rng: Random,
    features: Features,
    spec: dict,
    target_sec: float = 60.0,
    weather: dict | None = None,
) -> dict:
    bpm = spec["bpm"]
    mode = spec["mode"]
    key = spec["key_root"]
    genre = spec["genre"]
    meter = spec["meter"]
    voicing_spread = _spread_for(features.warmth)
    cloud_pct = float((weather or {}).get("cloud_pct", 50.0))
    drone_on = cloud_pct >= 70.0  # cloudy day → fog-drone
    drone_events: list[dict] = []
    motif = spec["motif"]
    bpb = _beats_per_bar(meter)

    sec_len = _section_lengths(genre, bpm, bpb, target_sec=target_sec)
    form = ["INTRO", "A", "B", "A_PRIME", "OUTRO"]
    total_bars = sum(sec_len[s] for s in form)

    # Build a single progression that spans all non-intro/outro sections,
    # with intro/outro pinned around tonic for stability.
    chord_seq: list[int] = []
    bars_meta: list[dict] = []

    intent_id = spec.get("intent_id")

    for section in form:
        n = sec_len[section]
        if section in ("INTRO", "OUTRO"):
            seq = [1] * n
            if section == "OUTRO" and n >= 2:
                seq[-2] = 4 if mode != "mixolydian" else 7
        else:
            cad = "tonic" if section == "A_PRIME" else "open"
            # Curated intent progressions take priority over the Markov
            # generator. Cron's auto song (intent_id is None) keeps the
            # Markov path so its sound stays familiar.
            seq = progression_for_intent(intent_id, rng, n,
                                         cadence=cad, mode=mode)
            if seq is None:
                seq = progression(rng, mode, n, cadence=cad)
        chord_seq.extend(seq)
        for d in seq:
            bars_meta.append({"section": section, "chord_degree": d, "beats": bpb})

    # melody over the whole sequence (intro/outro included; intro often sparse)
    melody_bars = melody_over_progression(rng, motif, chord_seq, bpb)

    # Wind shapes note density: still day -> thin out short notes,
    # windy day -> insert stepwise passing tones. Stays inside the
    # Muji-leaning ceiling because the rule only fires at the
    # extremes (< 0.30 or > 0.60 of the wind factor).
    wind_factor = max(0.0, min(1.0,
                               float((weather or {}).get("wind_mps", 2)) / 8.0))
    melody_bars = _apply_wind_density(melody_bars, wind_factor, rng)

    voicing = voicing_for_genre(genre)
    melody_events = []
    harmony_events = []
    bass_events = []
    percussion_events = []

    last_bar_idx = len(chord_seq) - 1
    cur_bar = 0
    ring_out_beats = 0.0  # extra ring for the closing chord
    for bar_idx, (chord_root, mel_notes, meta) in enumerate(
        zip(chord_seq, melody_bars, bars_meta)
    ):
        section = meta["section"]
        is_final = bar_idx == last_bar_idx

        # ── melody: skip on the very first INTRO bar and the very last
        #          OUTRO bar so the piece breathes in and out
        play_melody = True
        if section == "INTRO" and bar_idx == 0:
            play_melody = False
        if is_final:
            play_melody = False

        if play_melody:
            t = 0.0
            for deg, oct_shift, dur in mel_notes:
                pitch = degree_to_midi(key, mode, deg, octave_shift=oct_shift,
                                       base_octave=5)
                if 36 <= pitch <= 96:
                    vel = 70 + int(rng.uniform(-6, 6))
                    if section == "OUTRO":
                        vel = max(40, vel - 12)
                    melody_events.append({
                        "bar": cur_bar,
                        "start_beat": round(t, 4),
                        "pitch": pitch,
                        "dur_beats": round(dur, 4),
                        "vel": vel,
                    })
                t += dur

        # ── harmony comping (rhythmic left hand). Final bar is forced
        #    to tonic + sustained ring-out so the piece breathes shut.
        chord_for_harmony = 1 if is_final else chord_root
        full_chord = chord_pitches(key, mode, chord_for_harmony,
                                   voicing=voicing, base_octave=3,
                                   spread=voicing_spread)
        if is_final:
            ring_out_beats = bpb * 1.0
            harmony_events.append({
                "bar": cur_bar,
                "start_beat": 0.0,
                "pitches": full_chord,
                "dur_beats": bpb + ring_out_beats,
                "vel": 42,
            })
        else:
            har_base_vel = 56 + int(rng.uniform(-3, 3))
            for off, dur, kind, vel_mult in harmony_pattern(genre, meter):
                pitches = chord_subset(full_chord, kind)
                if not pitches:
                    continue
                vel = max(28, min(96,
                          int(round(har_base_vel * vel_mult
                                    + rng.uniform(-2, 2)))))
                harmony_events.append({
                    "bar": cur_bar,
                    "start_beat": round(off, 4),
                    "pitches": pitches,
                    "dur_beats": round(dur, 4),
                    "vel": vel,
                })

        # ── bass walking. Final bar = sustained root.
        if is_final:
            bass_root = degree_to_midi(key, mode, chord_for_harmony,
                                       octave_shift=-1, base_octave=2)
            bass_events.append({
                "bar": cur_bar, "start_beat": 0.0,
                "pitch": bass_root,
                "dur_beats": bpb + ring_out_beats,
                "vel": 50,
            })
        else:
            for off, dur, kind in bass_pattern(genre, meter):
                pitch = _bass_pitch(degree_to_midi, key, mode,
                                    chord_root, kind)
                if not (24 <= pitch <= 60):
                    continue
                vel = 58 + int(rng.uniform(-3, 3))
                # accent the downbeat; alberti upper notes softer
                if off == 0.0:
                    vel += 4
                if kind == "fifth_up":
                    vel -= 6
                bass_events.append({
                    "bar": cur_bar,
                    "start_beat": round(off, 4),
                    "pitch": pitch,
                    "dur_beats": round(dur, 4),
                    "vel": max(30, min(85, vel)),
                })

        # ── percussion: defines the pulse so the listener can feel
        #    time even when chord changes are slow. Stays silent in
        #    INTRO[0], OUTRO, and entirely for ambient.
        if not is_final and not (section == "INTRO" and bar_idx == 0):
            for off, kind, vel_mult in percussion_pattern(genre, meter):
                # fade percussion in over the INTRO and out over the OUTRO
                fade = 1.0
                if section == "INTRO":
                    fade = 0.55
                elif section == "OUTRO":
                    fade = 0.6
                vel = int(round(70 * vel_mult * fade
                                + rng.uniform(-2, 2)))
                vel = max(20, min(100, vel))
                percussion_events.append({
                    "bar": cur_bar,
                    "start_beat": round(off, 4),
                    "kind": kind,
                    "vel": vel,
                })

        cur_bar += 1

    # ── drone (cloudy days). One sustained tonic per section, very low,
    #    very quiet. Acts like fog under the mix.
    if drone_on:
        drone_pitch = degree_to_midi(key, mode, 1, octave_shift=-2,
                                     base_octave=2)
        bar_cursor = 0
        for s in form:
            n = sec_len[s]
            if n <= 0:
                continue
            vel_section = {
                "INTRO":   24,
                "A":       32,
                "B":       30,
                "A_PRIME": 32,
                "OUTRO":   24,
            }.get(s, 28)
            drone_events.append({
                "bar": bar_cursor,
                "start_beat": 0.0,
                "pitch": drone_pitch,
                "dur_beats": n * bpb,
                "vel": vel_section,
            })
            bar_cursor += n

    # ── humanization passes (deterministic via salted RNG) ──────────
    # Section breaks become phrase boundaries for the velocity arch.
    section_break_bars: list[int] = []
    acc = 0
    for s in form:
        section_break_bars.append(acc)
        acc += sec_len[s]
    outro_start_bar = total_bars - sec_len["OUTRO"]

    apply_velocity_curve(
        melody_events, rng,
        section_breaks=section_break_bars,
    )
    apply_outro_decay(melody_events, outro_start_bar)
    apply_micro_timing(melody_events, rng, jitter_beats=0.018)

    pedals = pedal_segments(
        genre=genre, total_bars=total_bars, bpb=bpb, chord_seq=chord_seq,
    )

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

    duration_beats = total_bars * bpb + ring_out_beats
    duration_sec = duration_beats * 60.0 / bpm

    return {
        "meta": {
            "date": date_iso,
            "city_id": city_id,
            "seed": seed,
            "generator_ver": GENERATOR_VER,
            "target_sec": target_sec,
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
            "melody":     melody_events,
            "harmony":    harmony_events,
            "bass":       bass_events,
            "percussion": percussion_events,
            "drone":      drone_events,
        },
        "voicing_spread": voicing_spread,
        "pedals": pedals,
        "signature": signature,
        "start_pitch": _pitch_class_name(start_pitch_midi),
        "ring_out_beats": ring_out_beats,
        "total_bars": total_bars,
        "duration_sec": round(duration_sec, 2),
    }


def write_ir(ir: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ir, fh, ensure_ascii=False, indent=2)
