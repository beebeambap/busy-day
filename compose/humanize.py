"""Humanization passes for the IR.

These run *after* the rule-based composer has produced bar-aligned
note events. They add what a player would naturally do but a
deterministic algorithm wouldn't: phrase-shaped dynamics, microscopic
timing wobble, and sustain-pedal markings.

All passes are deterministic given the seeded RNG that's threaded in.
"""

from __future__ import annotations

from random import Random

# Genres whose primary instrument expects sustain-pedal usage. Plucked
# / damped instruments (bossa, jazz Rhodes) sound worse with constant
# pedal so they're excluded.
PEDAL_GENRES = {"ambient", "neo_classical", "folk", "lo_fi"}


def apply_velocity_curve(
    events: list[dict],
    rng: Random,
    *,
    base: int = 56,
    span: int = 38,
    jitter: int = 6,
    section_breaks: list[int] | None = None,
) -> list[dict]:
    """Shape a phrase as a soft arch (low → peak ≈ middle → low).

    `section_breaks` is a list of bar indices that begin a new phrase.
    Velocities reset to `base` at each break and rise/fall around a
    randomly-placed peak (40-60% through the phrase).
    """
    if not events:
        return events

    breaks = sorted(set([0] + (section_breaks or []) + [events[-1]["bar"] + 1]))
    # Group events by phrase
    phrases: list[list[int]] = []
    cur: list[int] = []
    bp_iter = iter(breaks[1:])
    next_break = next(bp_iter, None)
    for i, ev in enumerate(events):
        while next_break is not None and ev["bar"] >= next_break:
            if cur:
                phrases.append(cur)
                cur = []
            next_break = next(bp_iter, None)
        cur.append(i)
    if cur:
        phrases.append(cur)

    for indices in phrases:
        n = len(indices)
        if n == 0:
            continue
        peak_pos = 0.45 + (rng.random() - 0.5) * 0.20  # 0.35 .. 0.55
        for k, idx in enumerate(indices):
            x = k / max(n - 1, 1)
            d = (x - peak_pos) / 0.6
            arch = max(0.0, 1.0 - d * d)
            v = base + span * arch + (rng.random() - 0.5) * 2 * jitter
            events[idx]["vel"] = max(28, min(112, int(round(v))))

    return events


def apply_outro_decay(events: list[dict], outro_start_bar: int) -> list[dict]:
    """Force a gradual decrescendo over the OUTRO so it doesn't snap shut."""
    outro = [e for e in events if e["bar"] >= outro_start_bar]
    if not outro:
        return events
    n = len(outro)
    for k, ev in enumerate(outro):
        x = k / max(n - 1, 1)
        ev["vel"] = max(20, int(round(ev["vel"] * (1.0 - 0.55 * x))))
    return events


def apply_micro_timing(
    events: list[dict],
    rng: Random,
    *,
    jitter_beats: float = 0.018,
) -> list[dict]:
    """Nudge note onsets by ±jitter_beats.

    Events that share the same (bar, start_beat) cluster get the SAME
    jitter offset, so a melody note and its harmony partner — both at
    e.g. bar=3, start_beat=2.0 — move together instead of drifting
    apart by up to 2*jitter_beats (= ~27 ms at 80 BPM, audible flam).
    """
    cluster_jitter: dict[tuple, float] = {}
    for ev in events:
        if "start_beat" not in ev:
            continue
        key = (ev.get("bar"), ev["start_beat"])
        if key not in cluster_jitter:
            cluster_jitter[key] = (rng.random() - 0.5) * 2 * jitter_beats
        ev["start_beat"] = round(
            max(0.0, ev["start_beat"] + cluster_jitter[key]),
            4,
        )
    return events


def apply_swing(events: list[dict], *, ratio: float = 1.67) -> list[dict]:
    """Re-time straight eighth notes as swung eighth pairs.

    Standard jazz swing: the "long-short" pair where the downbeat-
    eighth lasts a 2/3-of-a-beat (or 3/5 for a more subtle "ballad
    swing"), and the off-beat-eighth lasts the remaining 1/3.

    `ratio` is the long:short proportion:
        2.00 → triplet swing (hard bop, fast)
        1.67 → standard swing
        1.50 → soft swing (ballad)
        1.00 → straight eighths (no-op)

    Algorithm:
      - For each event with start_beat at the off-eighth of a beat
        (frac ≈ 0.5), shift to `beat + long_frac` where
        long_frac = ratio / (ratio + 1).
      - If the event has eighth-note duration (~0.5), shorten it to
        `(1 - long_frac)`, the off-eighth's swung duration.
      - For events ON the downbeat with eighth-note duration, extend
        the duration to `long_frac` so the downbeat eighth lasts the
        full long-portion of the swung pair.

    Sixteenths, quarters, halves, and any non-eighth subdivision are
    left untouched — swing is a property of the eighth-note grid.
    """
    if ratio <= 1.0:
        return events
    long_frac  = ratio / (ratio + 1.0)
    short_frac = 1.0 - long_frac

    for ev in events:
        b = ev.get("start_beat")
        if b is None:
            continue
        int_b = int(b)
        frac  = b - int_b
        d = ev.get("dur_beats", 0.0)
        is_eighth_dur = abs(d - 0.5) < 0.05

        # off-eighth (0.5): shift to long_frac inside the beat
        if abs(frac - 0.5) < 0.05:
            ev["start_beat"] = round(int_b + long_frac, 4)
            if is_eighth_dur:
                ev["dur_beats"] = round(short_frac, 4)
        # downbeat eighth: stretch dur to long_frac
        elif abs(frac) < 0.05 and is_eighth_dur:
            ev["dur_beats"] = round(long_frac, 4)
    return events


def apply_groove_delay(
    events: list[dict],
    *,
    delay_beats: float,
    skip_kinds: tuple[str, ...] = (),
) -> list[dict]:
    """Shift every event later by `delay_beats`.

    Used to push the performance slightly behind the beat — the "lazy
    drag" feel of RAIN's café-jazz preset (design doc: "비트를 약간
    뒤로"). A typical value at 80 BPM is +18 ms = ~0.024 beats; the
    caller is responsible for converting ms ↔ beats given the song's
    tempo.

    `skip_kinds` lets the caller exclude tracks that should remain on
    the grid (typically percussion, since the drummer is the timing
    reference even when the soloist drags).
    """
    if delay_beats <= 0.0:
        return events
    for ev in events:
        if ev.get("kind") in skip_kinds:
            continue
        b = ev.get("start_beat")
        if b is None:
            continue
        ev["start_beat"] = round(b + delay_beats, 4)
    return events


def apply_grace_notes(
    events: list[dict],
    rng: Random,
    *,
    prob: float = 0.15,
    min_dur_beats: float = 0.4,
) -> list[dict]:
    """Insert a 1/16-beat grace note one scale step away just before
    a held melody note. Adds the lilting Celtic/Muji ornamentation
    that mechanical motif variation can't produce.

    Returns a new event list (don't mutate input order in place).
    Events are kept sorted by (bar, start_beat).
    """
    if not events:
        return events
    GRACE = 0.0625      # 1/16 note relative to beat
    out: list[dict] = []
    for ev in events:
        # need a `pitch` field and enough room to carve off a 1/16
        dur = float(ev.get("dur_beats", 0))
        if "pitch" in ev and dur >= min_dur_beats and rng.random() < prob:
            offset = ev["start_beat"] - GRACE
            if offset >= 0.0:
                grace_pitch = ev["pitch"] + (1 if rng.random() < 0.5 else -1)
                # diatonic-safe-ish: cap so we don't wander too far. We
                # don't have direct mode access here, so a chromatic
                # neighbour ±1 is fine for an instant grace note.
                out.append({
                    "bar":        ev["bar"],
                    "start_beat": round(offset, 4),
                    "pitch":      int(grace_pitch),
                    "dur_beats":  GRACE,
                    "vel":        max(20, int(ev.get("vel", 60) * 0.55)),
                })
        out.append(ev)
    return out


def pedal_segments(
    *,
    genre: str,
    total_bars: int,
    bpb: float,
    chord_seq: list[int],
) -> list[dict]:
    """Return [{bar, on, off}] of damper-pedal-down windows.

    Convention: press at the bar's downbeat, release just before the
    next downbeat so the pedal change syncs with chord changes (no
    smearing across chords). When two adjacent bars share the same
    chord-degree we extend the pedal across the bar line for a smoother
    legato.
    """
    if genre not in PEDAL_GENRES:
        return []
    out: list[dict] = []
    b = 0
    while b < total_bars:
        end = b + 1
        # extend while next bar repeats the same chord
        while end < total_bars and chord_seq[end] == chord_seq[b]:
            end += 1
        out.append({
            "from_bar": b,
            "on": 0.0,
            "to_bar": end - 1,
            "off": bpb - 0.05,
        })
        b = end
    return out
