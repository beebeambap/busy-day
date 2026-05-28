"""Genre-style arrangement presets + selection rule.

Each preset is a same-genre re-interpretation of a source song. The
preset's `sub_style` drives which cell pack the comping picker uses
during transform; optional `voicing` / `bpm_multiplier` / etc.
override musical knobs further (parallel to weather-tape presets).

Phase 1a: 2 presets per genre — the genre's default sub-style + one
contrasting "deepening" alternate. Phase 2 will add 3rd options
(samba / stomp / swing / film / romantic / ambient lofi).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class StylePreset:
    """Same shape as TapePreset where attributes overlap, so the same
    transform_ir() can consume either. Adds `sub_style` which drives
    comping picker (comping.py _SUB_PACKS lookup)."""
    id: str                       # preset id, e.g. "bossa_jazz"
    label_ko: str                 # UI display label
    icon: str                     # UI icon, e.g. "🎷"
    source_genre: str             # this preset applies when source.genre == this
    genre_override: str           # what transform sets genre to (usually same)
    sub_style: str                # passed to comping picker → cell pack
    voicing: str = "triad"        # left-hand voicing override
    bpm_multiplier: float = 1.0
    melody_instrument: Optional[str] = None
    velocity_profile: dict = field(default_factory=dict)
    swing_ratio: Optional[float] = None
    groove_delay_ms: float = 0.0


# Each genre has 2 presets here. The "default" one (basica / boom_chick /
# walking / pad / alberti / chill) doesn't have a registered sub-style
# cell pack — comping falls back to the genre-default cells. The other
# preset is the "deepening" alternate (jazz / celtic / rubato / drone /
# pedal / boombap), with registered _SUB_PACKS entries.
STYLE_PRESETS: dict[str, StylePreset] = {
    # ── bossa_nova ─────────────────────────────────────────────────
    "bossa_basica": StylePreset(
        id="bossa_basica",
        label_ko="정통 보사",
        icon="🌴",
        source_genre="bossa_nova",
        genre_override="bossa_nova",
        sub_style="basica",
        voicing="seventh",
        # Brighter, upbeat Astrud-style bossa — more energy than source.
        bpm_multiplier=1.05,
        melody_instrument="nylon",
        velocity_profile={"melody": (62, 30), "harmony": (52, 22),
                          "bass": (58, 22)},
    ),
    "bossa_jazz": StylePreset(
        id="bossa_jazz",
        label_ko="재즈 후기 (Jobim)",
        icon="🎷",
        source_genre="bossa_nova",
        genre_override="bossa_nova",
        sub_style="jazz",
        voicing="ninth",
        # Slower, swung, behind-beat — Jobim's later ballad jazz feel.
        bpm_multiplier=0.85,                    # was 0.95
        melody_instrument="rhodes",
        velocity_profile={"melody": (50, 24), "harmony": (40, 16),
                          "bass": (48, 16)},   # quieter than source
        swing_ratio=1.30,                       # subtle bossa-jazz swing
        groove_delay_ms=12.0,                   # gentle behind-beat
    ),

    # ── folk ────────────────────────────────────────────────────────
    "folk_boomchick": StylePreset(
        id="folk_boomchick",
        label_ko="정통 부엉-칙",
        icon="🪕",
        source_genre="folk",
        genre_override="folk",
        sub_style="boom_chick",
        voicing="triad",
        # More energetic — Tom Petty / Americana drive.
        bpm_multiplier=1.05,
        melody_instrument="nylon",
        velocity_profile={"melody": (64, 30), "harmony": (54, 24),
                          "bass": (60, 22)},
    ),
    "folk_celtic": StylePreset(
        id="folk_celtic",
        label_ko="켈틱 드론",
        icon="🌿",
        source_genre="folk",
        genre_override="folk",
        sub_style="celtic",
        voicing="open_fifth",
        # Significantly slower for the drone/lament feel.
        bpm_multiplier=0.82,                    # was 0.92
        melody_instrument="harp",
        velocity_profile={"melody": (48, 22), "harmony": (38, 16),
                          "bass": (46, 16)},
    ),

    # ── jazz_ballad ─────────────────────────────────────────────────
    "jazz_walking": StylePreset(
        id="jazz_walking",
        label_ko="walking 베이스",
        icon="🎼",
        source_genre="jazz_ballad",
        genre_override="jazz_ballad",
        sub_style="walking",
        voicing="seventh",
        bpm_multiplier=1.05,                    # slight energy push
        melody_instrument="piano",
        velocity_profile={"melody": (58, 28), "harmony": (48, 20),
                          "bass": (56, 20)},
        swing_ratio=1.25,                       # light classic-jazz swing
    ),
    "jazz_rubato": StylePreset(
        id="jazz_rubato",
        label_ko="루바토 (Bill Evans)",
        icon="🕯",
        source_genre="jazz_ballad",
        genre_override="jazz_ballad",
        sub_style="rubato",
        voicing="ninth",
        # Truly rubato — drop another 10% from before for pause feel.
        bpm_multiplier=0.75,                    # was 0.85
        melody_instrument="piano",
        velocity_profile={"melody": (44, 22), "harmony": (36, 14),
                          "bass": (42, 14)},   # very soft
        groove_delay_ms=22.0,                   # loose behind-beat
    ),

    # ── ambient ─────────────────────────────────────────────────────
    "amb_pad": StylePreset(
        id="amb_pad",
        label_ko="패드",
        icon="☁",
        source_genre="ambient",
        genre_override="ambient",
        sub_style="amb_pad_default",            # → genre fallback cells
        voicing="triad",
        # Standard pad but with a small lift in dynamics so it doesn't
        # feel identical to a sleepier source.
        bpm_multiplier=1.0,
        velocity_profile={"melody": (58, 26), "harmony": (48, 22),
                          "bass": (54, 20)},
    ),
    "amb_drone": StylePreset(
        id="amb_drone",
        label_ko="드론",
        icon="🌫",
        source_genre="ambient",
        genre_override="ambient",
        sub_style="drone",
        voicing="open_fifth",
        # Deep slowdown for the contemplative drone.
        bpm_multiplier=0.78,                    # was 0.88
        velocity_profile={"melody": (42, 20), "harmony": (34, 14),
                          "bass": (38, 12)},
    ),

    # ── neo_classical ───────────────────────────────────────────────
    "neo_alberti": StylePreset(
        id="neo_alberti",
        label_ko="알베르티",
        icon="🎹",
        source_genre="neo_classical",
        genre_override="neo_classical",
        sub_style="neo_alberti_default",
        voicing="triad",
        bpm_multiplier=1.05,                    # crisper alberti runs
        velocity_profile={"melody": (62, 30), "harmony": (52, 22),
                          "bass": (58, 22)},
    ),
    "neo_pedal": StylePreset(
        id="neo_pedal",
        label_ko="페달 포인트",
        icon="🕊",
        source_genre="neo_classical",
        genre_override="neo_classical",
        sub_style="pedal",
        voicing="seventh",
        # Deeper slowdown for the held-pedal contemplation.
        bpm_multiplier=0.82,                    # was 0.95
        velocity_profile={"melody": (50, 24), "harmony": (42, 18),
                          "bass": (46, 16)},
    ),

    # ── lo_fi ───────────────────────────────────────────────────────
    "lofi_chill": StylePreset(
        id="lofi_chill",
        label_ko="칠",
        icon="🌙",
        source_genre="lo_fi",
        genre_override="lo_fi",
        sub_style="lofi_chill_default",
        voicing="triad",
        bpm_multiplier=0.95,
        velocity_profile={"melody": (54, 24), "harmony": (44, 18),
                          "bass": (50, 18)},
        groove_delay_ms=10.0,                   # gentle lazy
    ),
    "lofi_boombap": StylePreset(
        id="lofi_boombap",
        label_ko="붐뱁",
        icon="🥁",
        source_genre="lo_fi",
        genre_override="lo_fi",
        sub_style="boombap",
        voicing="seventh",
        # Heavier boom-bap shell, J Dilla micro-syncopation.
        bpm_multiplier=0.85,                    # was 0.95
        velocity_profile={"melody": (52, 24), "harmony": (42, 16),
                          "bass": (58, 22)},   # bass louder (sub-bass)
        swing_ratio=1.20,                       # light Dilla shuffle
        groove_delay_ms=18.0,                   # behind-beat
    ),
}


# ── selection rule (mood-driven) ──────────────────────────────────
# Each genre returns an ordered list of preset ids by preference. The
# chooser walks the list and picks the first whose sub_style differs
# from the source's current sub_style (avoids "same as source" trivial
# arrangements). Phase 1a: 2-option lists; Phase 2 can extend to 3.

def _rule_bossa(f: dict) -> list[str]:
    if f.get("calmness", 0.5) >= 0.65:
        return ["bossa_jazz", "bossa_basica"]   # 잔잔 → 재즈 발라드 풍
    return ["bossa_basica", "bossa_jazz"]       # 그 외 → 정통 보사


def _rule_folk(f: dict) -> list[str]:
    # wetness 또는 (잔잔 + 어두움) → 켈틱 드론
    if f.get("wetness", 0.0) >= 0.40 or (
            f.get("calmness", 0.5) >= 0.65 and f.get("brightness", 0.5) < 0.55):
        return ["folk_celtic", "folk_boomchick"]
    return ["folk_boomchick", "folk_celtic"]


def _rule_jazz(f: dict) -> list[str]:
    if f.get("calmness", 0.5) >= 0.70:
        return ["jazz_rubato", "jazz_walking"]
    return ["jazz_walking", "jazz_rubato"]


def _rule_ambient(f: dict) -> list[str]:
    if f.get("wetness", 0.0) >= 0.50 or f.get("calmness", 0.5) >= 0.75:
        return ["amb_drone", "amb_pad"]
    return ["amb_pad", "amb_drone"]


def _rule_neo(f: dict) -> list[str]:
    if f.get("calmness", 0.5) >= 0.65:
        return ["neo_pedal", "neo_alberti"]
    return ["neo_alberti", "neo_pedal"]


def _rule_lofi(f: dict) -> list[str]:
    if f.get("wetness", 0.0) >= 0.50 and f.get("brightness", 0.5) < 0.50:
        return ["lofi_boombap", "lofi_chill"]
    return ["lofi_chill", "lofi_boombap"]


_RULES = {
    "bossa_nova":    _rule_bossa,
    "folk":          _rule_folk,
    "jazz_ballad":   _rule_jazz,
    "ambient":       _rule_ambient,
    "neo_classical": _rule_neo,
    "lo_fi":         _rule_lofi,
}


def applicable_for_genre(genre: str) -> list[StylePreset]:
    """All style presets that apply to a given genre."""
    return [p for p in STYLE_PRESETS.values() if p.source_genre == genre]


def _effective_sub_style(s: Optional[str]) -> Optional[str]:
    """Normalize the '_default' sentinel and None to a single value so
    a 'default-preset arrangement of a source already using genre
    defaults' is detected as a no-op conflict (and skipped)."""
    if not s:
        return None
    if s.endswith("_default"):
        return None
    return s


def choose_for_source(source_ir: dict) -> Optional[StylePreset]:
    """Pick the best style preset for a source IR.

    Walks the genre's rule output (ordered preferences) and returns the
    first preset whose effective sub_style differs from the source's
    current sub_style. Effective = '_default' sentinel collapsed to None
    (so an ambient source with sub_style=None never gets the amb_pad
    preset, which would just regenerate the same default sound).

    Features come from the source IR's stored `features` dict — fully
    determined by the source song, no re-fetching weather or user input.
    Returns None if the source's genre has no rule defined.
    """
    genre = source_ir.get("spec", {}).get("genre")
    if genre not in _RULES:
        return None
    features = source_ir.get("features") or {}
    current = _effective_sub_style(source_ir.get("spec", {}).get("sub_style"))
    ranked = _RULES[genre](features)
    for pid in ranked:
        preset = STYLE_PRESETS.get(pid)
        if preset is None:
            continue
        if _effective_sub_style(preset.sub_style) != current:
            return preset
    # All conflict (shouldn't happen with 2+ options of differing kind).
    return STYLE_PRESETS.get(ranked[-1]) if ranked else None
