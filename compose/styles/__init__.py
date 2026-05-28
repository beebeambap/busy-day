"""Genre-style arrangement — same-genre re-interpretations.

Mirrors compose/tapes/ but the transformation stays within the source
song's genre (e.g., a bossa nova source → a different bossa nova
sub-style). The trigger is rule-based on the source song's own
features, NOT a user menu pick — matching the product's "조건 → 룰 →
결정" philosophy (the weather-tape pattern).

Usage flow:
  1. choose_for_source(source_ir) → StylePreset
  2. transform_ir(source_ir, preset, rng) → new IR
  3. render + upload (Phase 1b: CLI command)
"""
