"""IR-level transform that applies a tape preset to a source song.

The transform preserves the song's identity (melody pitches, chord
degrees, key, mode, meter, motif) and re-renders the accompaniment
according to the preset. The output is a fresh IR dict ready for
render.py / score.py to consume.

The transform is deterministic given (source IR, preset, seed) — the
caller passes an RNG so the same source + preset + seed always
produces the same tape variant.
"""

from __future__ import annotations

import hashlib
from random import Random

from ..comping import (
    bass_pattern_for,
    bass_pitch as _bass_pitch,
    chord_subset,
    harmony_pattern_for,
    percussion_pattern_for,
)
from ..humanize import (
    apply_groove_delay,
    apply_outro_decay,
    apply_swing,
    apply_velocity_curve,
    pedal_segments,
)
from ..scales import chord_pitches, degree_to_midi
from .presets import TapePreset


_BPM_FLOOR = 50
_BPM_CEIL  = 140


def _section_break_bars(form: list[str], sec_len: dict[str, int]) -> list[int]:
    """Bar indices where each section starts — used by velocity arch."""
    breaks: list[int] = []
    acc = 0
    for s in form:
        breaks.append(acc)
        acc += sec_len.get(s, 0)
    return breaks


def _rebuild_harmony_bar(
    *,
    bar_idx: int,
    section: str,
    chord_for_harmony: int,
    is_final: bool,
    key: str,
    mode: str,
    meter: str,
    genre: str,
    voicing: str,
    voicing_spread: str,
    bpb: float,
    rng: Random,
    sub_style: str | None = None,
) -> tuple[list[dict], float]:
    """Build harmony events for a single bar. Returns (events, ring_out_beats)."""
    full_chord = chord_pitches(
        key, mode, chord_for_harmony,
        voicing=voicing, base_octave=3, spread=voicing_spread,
    )
    events: list[dict] = []
    ring_out = 0.0

    if is_final:
        # final bar: sustained tonic ring-out (parallel to arrange.compose_ir)
        ring_out = bpb * 1.0
        events.append({
            "bar": bar_idx,
            "start_beat": 0.0,
            "pitches": full_chord,
            "dur_beats": bpb + ring_out,
            "vel": 42,
        })
        return events, ring_out

    har_base_vel = 56 + int(rng.uniform(-3, 3))
    for off, dur, kind, vel_mult in harmony_pattern_for(
        genre, meter, section, rng, sub_style=sub_style,
    ):
        pitches = chord_subset(full_chord, kind)
        if not pitches:
            continue
        vel = max(28, min(96, int(round(
            har_base_vel * vel_mult + rng.uniform(-2, 2),
        ))))
        events.append({
            "bar": bar_idx,
            "start_beat": round(off, 4),
            "pitches": pitches,
            "dur_beats": round(dur, 4),
            "vel": vel,
        })
    return events, ring_out


def _rebuild_bass_bar(
    *,
    bar_idx: int,
    section: str,
    chord_root: int,
    chord_for_harmony: int,
    is_final: bool,
    key: str,
    mode: str,
    meter: str,
    genre: str,
    bpb: float,
    ring_out: float,
    rng: Random,
    sub_style: str | None = None,
) -> list[dict]:
    events: list[dict] = []
    if is_final:
        bass_root = degree_to_midi(
            key, mode, chord_for_harmony, octave_shift=-1, base_octave=2,
        )
        events.append({
            "bar": bar_idx, "start_beat": 0.0,
            "pitch": bass_root,
            "dur_beats": bpb + ring_out,
            "vel": 50,
        })
        return events

    for off, dur, kind in bass_pattern_for(genre, meter, section, rng,
                                            sub_style=sub_style):
        pitch = _bass_pitch(degree_to_midi, key, mode, chord_root, kind)
        if not (24 <= pitch <= 60):
            continue
        vel = 58 + int(rng.uniform(-3, 3))
        if off == 0.0:
            vel += 4
        if kind == "fifth_up":
            vel -= 6
        events.append({
            "bar": bar_idx,
            "start_beat": round(off, 4),
            "pitch": pitch,
            "dur_beats": round(dur, 4),
            "vel": max(30, min(85, vel)),
        })
    return events


def _rebuild_percussion_bar(
    *,
    bar_idx: int,
    section: str,
    is_first_intro_bar: bool,
    is_final: bool,
    meter: str,
    genre: str,
    rng: Random,
    sub_style: str | None = None,
) -> list[dict]:
    if is_final or is_first_intro_bar:
        return []
    events: list[dict] = []
    fade = 1.0
    if section == "INTRO":
        fade = 0.55
    elif section == "OUTRO":
        fade = 0.6
    for off, kind, vel_mult in percussion_pattern_for(
            genre, meter, section, rng, sub_style=sub_style):
        vel = int(round(70 * vel_mult * fade + rng.uniform(-2, 2)))
        events.append({
            "bar": bar_idx,
            "start_beat": round(off, 4),
            "kind": kind,
            "vel": max(20, min(100, vel)),
        })
    return events


def transform_ir(
    original_ir: dict,
    preset: TapePreset,
    rng: Random,
) -> dict:
    """Apply `preset` to `original_ir`. Returns a fresh IR dict.

    Pure function — does not mutate `original_ir`. Determinism comes
    from the caller's `rng` (seed both the original-IR generation and
    this transform from the same source if reproducibility is needed).
    """
    spec_src = original_ir["spec"]
    key     = spec_src["key_root"]
    mode    = spec_src["mode"]
    meter   = spec_src["meter"]
    bpb     = float(meter.split("/")[0])

    new_bpm = round(spec_src["bpm"] * preset.bpm_multiplier)
    new_bpm = max(_BPM_FLOOR, min(_BPM_CEIL, new_bpm))

    new_genre = preset.genre_override
    voicing   = preset.voicing
    voicing_spread = original_ir.get("voicing_spread", "default")
    # Style presets carry a sub_style (drives comping picker → cell pack).
    # Tape presets don't define this attribute → falls back to None →
    # comping picker uses genre defaults (existing tape behavior unchanged).
    sub_style = getattr(preset, "sub_style", None)
    # The "default" style presets use sentinel sub_style ids ending in
    # "_default" to indicate "fall back to genre default cells". Normalize
    # to None so comping's _resolve_cells lookup doesn't try to find a
    # registered pack that doesn't exist.
    if sub_style and sub_style.endswith("_default"):
        sub_style = None

    bars_meta = original_ir["bars"]
    total_bars = len(bars_meta)
    last_bar_idx = total_bars - 1

    # melody preserved: deep-copy events so caller mutations don't bleed
    melody_events = [dict(e) for e in original_ir["tracks"]["melody"]]

    harmony_events: list[dict] = []
    bass_events: list[dict] = []
    percussion_events: list[dict] = []
    ring_out_beats = 0.0

    for bar_idx, meta in enumerate(bars_meta):
        section = meta["section"]
        chord_root = int(meta["chord_degree"])
        is_final = bar_idx == last_bar_idx
        chord_for_harmony = 1 if is_final else chord_root

        h_events, ring = _rebuild_harmony_bar(
            bar_idx=bar_idx, section=section,
            chord_for_harmony=chord_for_harmony, is_final=is_final,
            key=key, mode=mode, meter=meter, genre=new_genre,
            voicing=voicing, voicing_spread=voicing_spread,
            bpb=bpb, rng=rng, sub_style=sub_style,
        )
        harmony_events.extend(h_events)
        if is_final:
            ring_out_beats = ring

        bass_events.extend(_rebuild_bass_bar(
            bar_idx=bar_idx, section=section,
            chord_root=chord_root, chord_for_harmony=chord_for_harmony,
            is_final=is_final, key=key, mode=mode, meter=meter,
            genre=new_genre, bpb=bpb, ring_out=ring_out_beats, rng=rng,
            sub_style=sub_style,
        ))

        percussion_events.extend(_rebuild_percussion_bar(
            bar_idx=bar_idx, section=section,
            is_first_intro_bar=(section == "INTRO" and bar_idx == 0),
            is_final=is_final, meter=meter, genre=new_genre, rng=rng,
            sub_style=sub_style,
        ))

    # ── humanize: re-apply velocity curves per preset profile ──────
    form = original_ir.get("form", ["INTRO", "A", "B", "A_PRIME", "OUTRO"])
    sec_len = original_ir.get("section_bars", {})
    breaks = _section_break_bars(form, sec_len)
    outro_start_bar = total_bars - sec_len.get("OUTRO", 2)

    vp = preset.velocity_profile or {}
    if "harmony" in vp:
        base, span = vp["harmony"]
        apply_velocity_curve(
            harmony_events, rng,
            base=base, span=span, jitter=4,
            section_breaks=breaks,
        )
    apply_outro_decay(harmony_events, outro_start_bar)

    if "bass" in vp:
        base, span = vp["bass"]
        apply_velocity_curve(
            bass_events, rng,
            base=base, span=span, jitter=4,
            section_breaks=breaks,
        )
    apply_outro_decay(bass_events, outro_start_bar)

    if "melody" in vp:
        # Melody velocities are baked into the source IR; rescale them
        # to the preset's base while preserving the relative shape
        # (so the source's velocity arch is honored, just transposed).
        target_base, _span = vp["melody"]
        if melody_events:
            avg_vel = sum(e["vel"] for e in melody_events) / len(melody_events)
            shift = target_base - avg_vel
            for ev in melody_events:
                ev["vel"] = max(28, min(110, int(round(ev["vel"] + shift))))

    # ── groove: swing + behind-the-beat ────────────────────────────
    # Applied AFTER velocity curves and BEFORE pedal/signature calcs so
    # the new timings are reflected in the rendered output. Order:
    #   1. swing first  — re-times the eighth grid
    #   2. groove-delay — shifts everything (except percussion) later
    # so we don't accidentally undo swing by delaying twice. Percussion
    # is excluded from groove-delay because the drummer is the time
    # reference even when the soloist drags.
    if preset.swing_ratio and preset.swing_ratio > 1.0:
        for track in (melody_events, harmony_events, bass_events,
                      percussion_events):
            apply_swing(track, ratio=preset.swing_ratio)
    if preset.groove_delay_ms > 0.0:
        # Convert ms to beats using the *tape's* (post-multiplier) BPM:
        # delay_beats = delay_ms × (BPM / 60_000)
        delay_beats = (preset.groove_delay_ms * new_bpm) / 60_000.0
        for track in (melody_events, harmony_events, bass_events):
            apply_groove_delay(track, delay_beats=delay_beats)

    pedals = pedal_segments(
        genre=new_genre, total_bars=total_bars,
        bpb=bpb, chord_seq=[int(b["chord_degree"]) for b in bars_meta],
    )

    drone_events = list(original_ir["tracks"].get("drone", []))

    # signature: derive from source + tape preset so this variant is
    # unique in the songs.signature 14-day anti-repetition memory.
    sig_input = (
        f"{original_ir.get('signature', '')}"
        f"|tape:{preset.id}|v:{voicing}|g:{new_genre}|bpm:{new_bpm}"
    )
    signature = hashlib.sha1(sig_input.encode()).hexdigest()[:16]

    duration_beats = total_bars * bpb + ring_out_beats
    duration_sec = duration_beats * 60.0 / new_bpm

    return {
        "meta": dict(original_ir["meta"]),
        "spec": {
            "key_root": key,
            "mode": mode,
            "genre": new_genre,
            "bpm": new_bpm,
            "meter": meter,
            "motif_id": spec_src.get("motif_id"),
            "voicing": voicing,
        },
        "features": dict(original_ir.get("features", {})),
        "form": list(form),
        "section_bars": dict(sec_len),
        "bars": [dict(b) for b in bars_meta],
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
        "start_pitch": original_ir.get("start_pitch"),
        "ring_out_beats": ring_out_beats,
        "total_bars": total_bars,
        "duration_sec": round(duration_sec, 2),
        "tape": {
            "id": preset.id,
            "source_signature": original_ir.get("signature"),
            "bpm_multiplier": preset.bpm_multiplier,
            "voicing": voicing,
            "genre_override": new_genre,
            "melody_instrument": preset.melody_instrument,
        },
    }
