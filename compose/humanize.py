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
    """Nudge note onsets by ±jitter_beats (independent per note)."""
    for ev in events:
        if "start_beat" in ev:
            ev["start_beat"] = round(
                max(0.0, ev["start_beat"] + (rng.random() - 0.5) * 2 * jitter_beats),
                4,
            )
    return events


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
