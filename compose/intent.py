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
        deltas={"brightness": +0.30, "warmth": +0.10, "calmness": -0.30},
        preferred_genre="bossa_nova",
        avoid_genres=("ambient", "lo_fi"),
        bpm_clamp=(92, 112),
    ),
    "after_rain": Intent(
        id="after_rain",
        label_ko="비 온 뒤처럼",
        deltas={"wetness": +0.30, "brightness": -0.10, "calmness": +0.20},
        bpm_clamp=(72, 90),
    ),
    "sleep": Intent(
        id="sleep",
        label_ko="잠들기 전",
        deltas={"brightness": -0.20, "calmness": +0.40, "warmth": +0.10},
        preferred_genre="ambient",
        bpm_clamp=(60, 70),
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
