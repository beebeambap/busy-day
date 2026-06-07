"""Per-weather tape presets.

Each preset is a fixed rule-set that re-arranges any source song into
a weather-themed variant. The melody pitches and chord-degree
progression are preserved; the preset overrides genre, voicing, BPM,
instrument timbre, and velocity profile.

Adding a preset = one entry below + (optionally) a clause in
match_weather() so the UI knows when to offer it.

Currently shipped:
  clear_hot  : sunny + hot summer days → Bossa Nova / Balearic feel
  rain       : rainy days → Acoustic Jazz café feel (Keith Jarrett /
               Novo Amor; "원곡을 비 내리는 카페 안에서 누군가
               피아노로 다시 치는 느낌")

Planned (designed in weather-tapes-arrangement-system-v1.md, not yet
implemented):
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

    Optional groove transforms:
      swing_ratio        if set (e.g. 1.50 for ballad, 1.67 for standard,
                         2.0 for triplet swing), eighth notes get re-timed
                         to the swung long-short pair. Anything ≤ 1.0
                         disables swing (straight eighths).
      groove_delay_ms    if > 0, every non-percussion event is shifted
                         later by this many ms (converted to beats using
                         the tape's BPM). Used for "behind-the-beat" feel.
    """
    id: str
    label_ko: str
    genre_override: str
    voicing: str
    bpm_multiplier: float
    melody_instrument: Optional[str] = None
    velocity_profile: dict = field(default_factory=dict)
    swing_ratio: Optional[float] = None
    groove_delay_ms: float = 0.0


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


RAIN = TapePreset(
    id="rain",
    label_ko="비 오는 날",
    # jazz_ballad is the closest single-genre match for "Acoustic Jazz
    # café" — gives us walking-bass cells, sparse comping, and the
    # rhodes_pad / upright harmony+bass palette out of the box.
    genre_override="jazz_ballad",
    # The 9th adds the "café piano" colour the design doc calls out
    # ("오픈 보이싱 + 9th 추가 — 공기감").
    voicing="ninth",
    # -12 % tempo: the design doc says "원본 대비 -10~15%". The slower
    # pulse reinforces the "창가에서 빗소리 들으며" stillness.
    bpm_multiplier=0.88,
    # Salamander grand piano: the Keith Jarrett "café piano" timbre.
    melody_instrument="piano",
    velocity_profile={
        # Right hand pp–mp so it floats; left hand quieter still so
        # the melody sits "수면 위로 뜨는 느낌". Numbers below CLEAR_HOT.
        "melody":  (48, 26),
        "harmony": (40, 18),
        "bass":    (44, 18),
    },
    # "미세 스윙": 1.50 ratio (3:2) is a soft "ballad swing" — present
    # but not the pronounced 2:1 hard-bop swing. The eighth pair
    # becomes 0.6:0.4 of a beat. Right for "카페 창가" feel.
    swing_ratio=1.50,
    # "비트를 약간 뒤로": +18 ms at the tape's BPM. At RAIN's typical
    # 70 BPM (after the 0.88 × multiplier on ~80 BPM sources) that's
    # 18/857 ≈ 0.021 beats — barely perceptible per note but adds the
    # "lazy drag" feel when accumulated across the whole performance.
    groove_delay_ms=18.0,
)


# ── new presets (Phase 2 weather expansion) ──────────────────────

# SNOW: winter music-box. Very slow, sparse, bell-like sparkle on a
# neo-classical pedal-point bed. Uses the neo_pedal sub-style cells we
# defined earlier (full-bar root + 3-beat sustain + 1-beat answer).
SNOW = TapePreset(
    id="snow",
    label_ko="눈 오는 날",
    genre_override="neo_classical",
    voicing="open_fifth",       # cold modal / hollow
    bpm_multiplier=0.78,        # very slow — snow stillness
    melody_instrument="music_box",
    velocity_profile={
        "melody":  (40, 18),    # whisper sparkle
        "harmony": (30, 12),    # barely there
        "bass":    (34, 10),
    },
)

# FOG: muffled ambient drone with breathy flute melody. Wide cloud +
# high humidity + no wind = the still suspended-air feeling.
FOG = TapePreset(
    id="fog",
    label_ko="안개 낀 날",
    genre_override="ambient",
    voicing="open_fifth",
    bpm_multiplier=0.82,
    melody_instrument="flute",
    velocity_profile={
        "melody":  (46, 20),
        "harmony": (34, 14),
        "bass":    (38, 12),
    },
)

# COLD_CLEAR: nordic folk on a frozen sunny day. Harp + open-fifth
# drone — the celtic sub-style cells already define this character.
COLD_CLEAR = TapePreset(
    id="cold_clear",
    label_ko="춥고 맑은 날",
    genre_override="folk",
    voicing="open_fifth",
    bpm_multiplier=0.92,
    melody_instrument="harp",
    velocity_profile={
        "melody":  (54, 22),
        "harmony": (42, 16),
        "bass":    (50, 16),
    },
)

# HUMID: stagnant summer day, smoky-jazz café. Like RAIN but no rain,
# warmer, and even more sluggish. Rhodes + rubato sub-style cells.
HUMID = TapePreset(
    id="humid",
    label_ko="장마같은 끈끈한 날",
    genre_override="jazz_ballad",
    voicing="ninth",
    bpm_multiplier=0.85,
    melody_instrument="rhodes",
    velocity_profile={
        "melody":  (48, 22),
        "harmony": (36, 16),
        "bass":    (46, 16),
    },
    swing_ratio=1.40,            # softer than RAIN's 1.50
    groove_delay_ms=15.0,
)

# WINDY: open-air folk with motion and lift. Tin whistle melody,
# uptempo, wide voicing spread (set by features-driven _spread_for).
WINDY = TapePreset(
    id="windy",
    label_ko="바람 부는 날",
    genre_override="folk",
    voicing="seventh",
    bpm_multiplier=1.10,         # forward push
    melody_instrument="tin_whistle",
    velocity_profile={
        "melody":  (64, 28),
        "harmony": (54, 22),
        "bass":    (58, 20),
    },
)

# STORM: dramatic dark cello on neo-classical pedal point. Bigger
# dynamic range than other presets (loud melody + deep bass).
STORM = TapePreset(
    id="storm",
    label_ko="폭풍 치는 날",
    genre_override="neo_classical",
    voicing="ninth",
    bpm_multiplier=0.92,
    melody_instrument="cello",
    velocity_profile={
        "melody":  (70, 32),     # dramatic
        "harmony": (54, 22),
        "bass":    (70, 24),     # deep + loud
    },
)

# COOL_CLEAR: clear_hot's cooler cousin. Sunday-morning folk feel —
# nylon, slight energy lift, no special groove.
COOL_CLEAR = TapePreset(
    id="cool_clear",
    label_ko="선선하고 맑은 날",
    genre_override="folk",
    voicing="triad",
    bpm_multiplier=1.05,
    melody_instrument="nylon",
    velocity_profile={
        "melody":  (64, 30),
        "harmony": (52, 22),
        "bass":    (58, 22),
    },
)


# SHOWER: passing summer rain. Heavier than light rain but short-lived —
# the "지나가는 소나기 후 햇살" feel. Lighter and more upbeat than RAIN
# (which is steady all-day overcast). Rhodes EP for café warmth + light
# swing for the lingering air freshness.
SHOWER = TapePreset(
    id="shower",
    label_ko="소나기 오는 날",
    genre_override="jazz_ballad",
    voicing="ninth",
    # Neutral tempo — keeps the source's energy. (RAIN is -12%, slow;
    # SHOWER is meant to feel transient, not heavy.)
    bpm_multiplier=1.00,
    # Rhodes — warmer/lighter than RAIN's grand piano. Reads as "café
    # at the moment the shower hits, not after hours of rain".
    melody_instrument="rhodes",
    velocity_profile={
        "melody":  (54, 26),    # brighter than RAIN's (48,26)
        "harmony": (44, 18),
        "bass":    (50, 18),
    },
    # Lighter swing than RAIN (1.30 vs 1.50) — the air feel is brisker.
    swing_ratio=1.30,
    # Smaller behind-beat lag than RAIN (10 vs 18 ms).
    groove_delay_ms=10.0,
)


PRESETS: dict[str, TapePreset] = {
    "clear_hot":  CLEAR_HOT,
    "rain":       RAIN,
    "shower":     SHOWER,
    "snow":       SNOW,
    "fog":        FOG,
    "cold_clear": COLD_CLEAR,
    "humid":      HUMID,
    "windy":      WINDY,
    "storm":      STORM,
    "cool_clear": COOL_CLEAR,
}


# ── API ────────────────────────────────────────────────────────────

def get(preset_id: str | None) -> TapePreset | None:
    if not preset_id:
        return None
    return PRESETS.get(preset_id)


def match_weather(weather: dict | None) -> str | None:
    """Return the preset id that matches `weather`, or None.

    Checked in order of specificity — the more unusual conditions
    (snow, storm) win over general ones (cool_clear, windy) so a
    snowy windy day shows "snow" not "windy". The UI only shows the
    matched preset's button.
    """
    if not weather:
        return None
    temp   = float(weather.get("temp_c",    15.0))
    cloud  = float(weather.get("cloud_pct", 50.0))
    precip = float(weather.get("precip_mm",  0.0))
    wind   = float(weather.get("wind_mps",   2.0))
    humid  = float(weather.get("humidity",  60.0))
    ptype  = str(weather.get("precip_type", "none"))

    # 1) SNOW — precip_type wins regardless of other conditions.
    if ptype in ("snow", "rain_snow"):
        return "snow"

    # 2) STORM — heavy rain + strong wind. Dramatic. (A shower with
    # storm-level wind/precip still reads as "storm" here.)
    if precip >= 5.0 and wind >= 5.0:
        return "storm"

    # 3) SHOWER — KMA precip_type code 4 (소나기). Convective short-
    # duration rain, distinct mood from steady all-day rain.
    if ptype == "shower":
        return "shower"

    # 4) RAIN — meaningful rain + overcast (existing).
    if precip >= 0.3 and cloud >= 50.0:
        return "rain"

    # 5) FOG — heavy cloud + humid + still air, no precip.
    if cloud >= 80.0 and humid >= 75.0 and wind < 3.0 and precip < 0.3:
        return "fog"

    # 6) CLEAR_HOT — hot + clear + dry (existing).
    if temp >= 25.0 and cloud <= 30.0 and precip <= 0.5:
        return "clear_hot"

    # 7) COLD_CLEAR — freezing + clear + dry.
    if temp <= 5.0 and cloud <= 50.0 and precip < 0.3 and humid < 65.0:
        return "cold_clear"

    # 8) HUMID — muggy summer, no rain.
    if humid >= 80.0 and temp >= 22.0 and precip < 0.5:
        return "humid"

    # 9) WINDY — strong wind, dry.
    if wind >= 5.0 and precip < 1.0:
        return "windy"

    # 10) COOL_CLEAR — fallback clear-sky preset for mild weather.
    if 12.0 <= temp <= 22.0 and cloud <= 30.0 and precip < 0.3:
        return "cool_clear"

    return None
