"""User-pickable instruments for the *melody* layer.

`instrument_id = None` means "let the genre decide" (the existing
default mapping). When set, the browser overrides the melody timbre
while harmony + bass still take their cue from the genre — so the
result is "violin over the same nylon-bossa pad", etc.

Instrument profiles are referenced by id in:
  - this file (server-side metadata + GM program for MIDI download)
  - js/player.js (client Tone.js synth recipes)
  - the web intent modal (label + emoji)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    id: str
    label_ko: str
    gm_program: int     # General MIDI program for downloaded .mid file
    icon: str           # short emoji/glyph for UI


INSTRUMENTS: dict[str, Instrument] = {
    "piano":     Instrument("piano",     "피아노",        0,  "🎹"),
    "rhodes":    Instrument("rhodes",    "일렉트릭 피아노", 4,  "🎹"),
    "nylon":     Instrument("nylon",     "나일론 기타",    24, "🎸"),
    "violin":    Instrument("violin",    "바이올린",       40, "🎻"),
    "viola":     Instrument("viola",     "비올라",         41, "🎻"),
    "cello":     Instrument("cello",     "첼로",           42, "🎻"),
    "strings":   Instrument("strings",   "현악기",         48, "🎻"),  # legacy alias
    "flute":     Instrument("flute",     "플루트",         73, "🎵"),
    "tin_whistle": Instrument("tin_whistle", "틴 휘슬",     74, "🎶"),
    "harp":      Instrument("harp",      "하프",           46, "🎶"),
    "marimba":   Instrument("marimba",   "마림바",         12, "🥁"),
    "music_box": Instrument("music_box", "음악 상자",      10, "🔔"),
    "horn":      Instrument("horn",      "호른",           60, "📯"),
}


def get(instrument_id: str | None) -> Instrument | None:
    if not instrument_id:
        return None
    return INSTRUMENTS.get(instrument_id)
