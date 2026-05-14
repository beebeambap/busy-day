"""Weather Tapes — theme-album arrangement system.

Transforms an existing song's IR into a weather-themed re-arrangement
while preserving the song's melodic identity (key, melody pitches,
chord-degree progression, bar structure).

Public API:
  PRESETS         dict mapping tape_id -> TapePreset
  TapePreset      dataclass describing one weather tape
  get(id)         fetch a preset by id (None if unknown)
  match_weather(w) -> tape_id | None
                  given a weather dict, return the matching preset id
                  that the UI should offer as the "arrange" button
  transform_ir(original_ir, preset, rng) -> dict
                  apply the preset's rules to the IR; returns a new IR
                  ready to feed render.py / score.py.
"""

from .presets import PRESETS, TapePreset, get, match_weather
from .transform import transform_ir

__all__ = ["PRESETS", "TapePreset", "get", "match_weather", "transform_ir"]
