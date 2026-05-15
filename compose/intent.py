"""User-supplied "feeling" maps to deterministic feature deltas + biases.

No LLM. Each preset is a tuned hand-crafted nudge on the same 4-d
feature space the rule-based composer already consumes, plus optional
hard biases for genre / mode / BPM range. The result is a different
song for the same day / weather, while staying inside the Muji-leaning
aesthetic.

Adding a preset = one entry below + one button in the web UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Intent:
    id: str
    label_ko: str
    deltas: dict          # feature -> delta in [-1, 1] (clipped to [0,1] after)
    preferred_genre: Optional[str] = None
    avoid_genres: tuple[str, ...] = ()
    mode_bias: Optional[str] = None    # only ionian/dorian/lydian/mixolydian
    bpm_clamp: Optional[tuple[int, int]] = None
    # Override the genre-driven meter pick. Used by intents whose mental
    # model implies a specific subdivision (산책 = 4/4 boom-chick aligned
    # with footsteps; a 3/4 walking song feels mismatched).
    force_meter: Optional[str] = None    # "3/4" | "4/4" | "6/8"


INTENTS: dict[str, Intent] = {
    "calm": Intent(
        id="calm",
        label_ko="차분하게",
        deltas={"calmness": +0.30, "brightness": -0.10},
        preferred_genre="ambient",
        bpm_clamp=(62, 76),
    ),
    "warm": Intent(
        id="warm",
        label_ko="따뜻하게",
        deltas={"warmth": +0.30, "calmness": +0.10, "wetness": -0.10},
        bpm_clamp=(72, 92),
    ),
    "wistful": Intent(
        id="wistful",
        label_ko="쓸쓸하게",
        deltas={"warmth": -0.10, "brightness": -0.30,
                "wetness": +0.10, "calmness": +0.20},
        mode_bias="dorian",
        avoid_genres=("bossa_nova", "folk"),
        bpm_clamp=(68, 84),
    ),
    "lively": Intent(
        id="lively",
        label_ko="활기차게",
        deltas={"brightness": +0.25, "warmth": +0.10, "calmness": -0.20},
        preferred_genre="folk",           # bossa_nova at 112 BPM was outside Muji range
        avoid_genres=("ambient", "lo_fi"),
        bpm_clamp=(86, 100),              # was (92, 112); 100 BPM is upbeat but still musical
    ),
    "after_rain": Intent(
        id="after_rain",
        label_ko="비 온 뒤처럼",
        deltas={"wetness": +0.30, "brightness": -0.10, "calmness": +0.20},
        # bVII-IV-I needs mixolydian to actually sound like the ♭VII;
        # in ionian the same degree sequence reads as vii°-IV-I.
        mode_bias="mixolydian",
        bpm_clamp=(72, 90),
    ),
    "sleep": Intent(
        id="sleep",
        label_ko="잠들기 전",
        deltas={"brightness": -0.20, "calmness": +0.40, "warmth": +0.10},
        preferred_genre="ambient",
        bpm_clamp=(60, 70),
    ),

    # ── 시간/상황 무드 (manual trigger only) ─────────────────────────
    # The auto cron always fires at 06:00 KST, so situational presets
    # only really make sense when the user is composing on demand.
    # These act like the emotional intents above (deltas + biases) but
    # carry a different label set so the UI can group them.
    "dawn": Intent(
        id="dawn",
        label_ko="새벽",
        deltas={"brightness": -0.30, "calmness": +0.45, "warmth": -0.10},
        preferred_genre="ambient",
        bpm_clamp=(50, 65),
    ),
    "commute": Intent(
        id="commute",
        label_ko="출근길",
        deltas={"brightness": +0.10, "calmness": -0.20},
        # Bumped from (75, 88). Real morning commute energy needs more
        # forward push — a 75 BPM song feels like a sleepy yoga class,
        # not a walk-to-the-subway pulse.
        bpm_clamp=(90, 104),
    ),
    "nap": Intent(
        id="nap",
        label_ko="낮잠",
        deltas={"brightness": -0.10, "calmness": +0.30, "warmth": +0.10},
        preferred_genre="ambient",
        bpm_clamp=(58, 72),
    ),
    "focus": Intent(
        id="focus",
        label_ko="작업 중",
        deltas={"brightness": +0.05, "calmness": +0.10},
        avoid_genres=("bossa_nova",),    # too "songy" for background work
        # Slight bump from (70, 84). Background music should not drag
        # so much that it pulls the listener toward sleep.
        bpm_clamp=(74, 90),
    ),
    "walk": Intent(
        id="walk",
        label_ko="산책",
        # calmness pushed harder negative so density modulation kicks in
        # (active intents trigger more passing tones — see arrange.py
        # _apply_activity_density).
        deltas={"brightness": +0.15, "warmth": +0.10, "calmness": -0.25},
        preferred_genre="folk",
        # Centered around 119 BPM — matches a typical brisk walking
        # cadence (110-125 steps per minute). Was (78, 94) — too slow,
        # felt like meditation rather than walking.
        bpm_clamp=(114, 124),
        # 4/4 boom-chick aligns with footsteps; 3/4 (waltz) and 6/8
        # both miss the walking pulse for the listener's mental model.
        force_meter="4/4",
    ),
}


def apply(intent: Intent, features) -> "Features":
    """Return new Features with deltas applied (clipped to [0, 1])."""
    from .features import Features
    f = features.as_dict()
    for k, v in intent.deltas.items():
        if k in f:
            f[k] = max(0.0, min(1.0, f[k] + v))
    return Features(**f)


def get(intent_id: str | None) -> Intent | None:
    if not intent_id:
        return None
    return INTENTS.get(intent_id)
