"""Per-weather tape presets.

Each preset is a fixed rule-set that re-arranges any source song into
a weather-themed variant. The melody pitches and chord-degree
progression are preserved; the preset overrides genre, voicing, BPM,
instrument timbre, and velocity profile.

Adding a preset = one entry below + (optionally) a clause in
match_weather() so the UI knows when to offer it.

Currently shipped:
  clear_hot  : sunny + hot summer days → Bossa Nova / Balearic feel

Planned (designed in weather-tapes-arrangement-system-v1.md, not yet
implemented):
  rain       : rainy days → Acoustic Jazz café feel
  cold       : freezing days → Nordic Folk / Scandinavian Ambient
  snow       : snowy days → ECM Minimal Classical
  fog        : foggy / overcast days → Ambient Drone / Shoegaze wash
  storm      : thunderstorm days → Post-Rock buildup structure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TapePreset:
    """One weather tape's transformation rule-set.

    Fixed in the transform regardless of preset:
      - melody event sequence (preserves song identity)
      - chord-degree progression
      - key, mode, motif

    Overridden by the preset:
      genre_override     swaps comping-cell library, percussion cells,
                         harmony/bass instrument palette (via player.js
                         genre defaults)
      voicing            "triad"|"seventh"|"ninth"|"open_fifth"
      bpm_multiplier     applied to spec.bpm
      melody_instrument  optional override (None = use genre default)
      velocity_profile   {"melody": (base, span), "harmony": (b,s),
                          "bass": (b,s)} — used by apply_velocity_curve
    """
    id: str
    label_ko: str
    genre_override: str
    voicing: str
    bpm_multiplier: float
    melody_instrument: Optional[str] = None
    velocity_profile: dict = field(default_factory=dict)


# ── presets ────────────────────────────────────────────────────────

CLEAR_HOT = TapePreset(
    id="clear_hot",
    label_ko="맑고 더운 날",
    # Force bossa_nova: gives us nylon-guitar harmony palette + upright
    # bass + shaker percussion automatically via existing player.js
    # genre defaults. No new palette plumbing needed.
    genre_override="bossa_nova",
    # 9th voicing = tropical "café" colour. The 2nd-scale-degree tension
    # one octave above the chord root is what makes a bossa chord sound
    # bossa, not just jazz-major.
    voicing="ninth",
    # Slight uptempo (+8%) for the "나른하지만 에너지" feel. We don't go
    # higher because clear_hot is still Muji-adjacent — café music, not
    # workout playlist.
    bpm_multiplier=1.08,
    # Nylon guitar melody to match the bossa palette. If the original
    # already used nylon (e.g. user picked it manually), this is a no-op.
    melody_instrument="nylon",
    velocity_profile={
        "melody":  (58, 30),    # base 58, span 30 — present without piercing
        "harmony": (50, 22),    # richer than default 44 (9th wants presence)
        "bass":    (56, 20),    # active upright
    },
)


PRESETS: dict[str, TapePreset] = {
    "clear_hot": CLEAR_HOT,
}


# ── API ────────────────────────────────────────────────────────────

def get(preset_id: str | None) -> TapePreset | None:
    if not preset_id:
        return None
    return PRESETS.get(preset_id)


def match_weather(weather: dict | None) -> str | None:
    """Return the preset id that matches `weather`, or None.

    Used by the UI to decide which "편곡하기" button to show on a song's
    detail panel. The criteria are intentionally narrow so a song only
    gets a tape button when the day genuinely fits the preset's mood.
    """
    if not weather:
        return None
    temp   = float(weather.get("temp_c",    15.0))
    cloud  = float(weather.get("cloud_pct", 50.0))
    precip = float(weather.get("precip_mm",  0.0))

    # CLEAR HOT: hot + sunny + dry. 25°C+ is summer-warm in Seoul;
    # cloud ≤ 30% reads as "clear"; precip threshold filters out
    # passing showers on otherwise-clear days.
    if temp >= 25.0 and cloud <= 30.0 and precip <= 0.5:
        return "clear_hot"

    return None
