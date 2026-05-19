"""End-to-end orchestration for one (date, city) song."""

from __future__ import annotations

from random import Random
from typing import Any

from . import GENERATOR_VER
from .arrange import compose_ir
from .features import extract
from .intent import Intent, apply as apply_intent
from .mapping import (
    pick_bass_octave_shift,
    pick_bpm,
    pick_genre,
    pick_key,
    pick_melody_octave,
    pick_meter,
    pick_mode,
    pick_motif,
    pick_oct_climb,
    pick_sub_bass,
    pick_sub_style,
    pick_use_ninth,
)
from .seed import make_seed, rng


def _decide_spec(
    seed: int,
    features,
    *,
    avoid_genres: list[str] | None,
    avoid_motifs: list[str] | None,
    preferred_genre: str | None,
    force_genre: str | None = None,
    intent: Intent | None = None,
    seed_salt: str = "",
) -> dict:
    """seed_salt lets us produce a different draw for the same date when
    the user requests a manual variant. The base seed (= same day = same
    auto song) stays untouched."""
    s = lambda label: rng(seed, f"{seed_salt}{label}")

    if intent and intent.mode_bias:
        mode = intent.mode_bias
    else:
        mode = pick_mode(s("mode"), features)

    key = pick_key(s("key"), features)

    eff_avoid = list(avoid_genres or [])
    if intent and intent.avoid_genres:
        eff_avoid.extend(intent.avoid_genres)
    pref = preferred_genre or (intent.preferred_genre if intent else None)
    genre = pick_genre(s("genre"), features,
                      avoid=eff_avoid, preferred=pref, force=force_genre)

    if intent and intent.bpm_clamp:
        # Intent-driven flow: sample directly from the intent's clamp
        # range. Previously we ran pick_bpm and then clamped — but
        # pick_bpm caps at 112 globally, so high-energy intents (산책
        # at 120 BPM target) couldn't reach their natural tempo.
        # Using the seeded RNG keeps determinism per (seed, intent).
        lo, hi = intent.bpm_clamp
        bpm = lo + s("bpm_in_clamp").randint(0, hi - lo)
    else:
        bpm = pick_bpm(s("bpm"), features, genre)

    if intent and intent.force_meter:
        meter = intent.force_meter
    else:
        meter = pick_meter(s("meter"), genre)
    motif = pick_motif(s("motif"), features,
                       avoid_ids=set(avoid_motifs or []))

    sub_style = pick_sub_style(s("sub_style"), genre)

    melody_octave = pick_melody_octave(s("mel_oct"), features)
    intent_id_for_climb = intent.id if intent else None
    oct_climb = pick_oct_climb(s("oct_climb"), features, intent_id_for_climb)
    sub_bass = pick_sub_bass(s("sub_bass"), features)
    bass_oct_shift = pick_bass_octave_shift(s("bass_oct"), features)
    use_ninth = pick_use_ninth(s("ninth"), features)

    return {
        "key_root": key, "mode": mode, "genre": genre,
        "bpm": bpm, "meter": meter, "motif": motif,
        "sub_style": sub_style,
        "melody_octave": melody_octave,
        "oct_climb": oct_climb,
        "sub_bass": sub_bass,
        "bass_oct_shift": bass_oct_shift,
        "use_ninth": use_ninth,
        "intent_id": intent.id if intent else None,
    }


def generate_pair(
    *,
    date_iso: str,
    city_id: str,
    weather: dict,
    short_sec: float = 60.0,
    long_sec: float = 130.0,
    avoid_genres: list[str] | None = None,
    avoid_motifs: list[str] | None = None,
    preferred_genre: str | None = None,
    force_genre: str | None = None,
    intent: Intent | None = None,
    seed_salt: str = "",
    generator_ver: str = GENERATOR_VER,
) -> tuple[dict, dict]:
    """Generate the short and long variants of the same song.

    Both share the (key, mode, genre, bpm, meter, motif) spec; only the
    form expands. The long variant is a natural extension, not a remix.
    """
    seed = make_seed(date_iso, city_id, generator_ver)
    features = extract(weather)
    if intent is not None:
        features = apply_intent(intent, features)

    spec = _decide_spec(
        seed, features,
        avoid_genres=avoid_genres,
        avoid_motifs=avoid_motifs,
        preferred_genre=preferred_genre,
        force_genre=force_genre,
        intent=intent,
        seed_salt=seed_salt,
    )

    ir_short = compose_ir(
        date_iso=date_iso, city_id=city_id, seed=seed,
        rng=rng(seed, f"{seed_salt}compose:short"),
        features=features, spec=spec, target_sec=short_sec,
        weather=weather,
    )
    ir_long = compose_ir(
        date_iso=date_iso, city_id=city_id, seed=seed,
        rng=rng(seed, f"{seed_salt}compose:long"),
        features=features, spec=spec, target_sec=long_sec,
        weather=weather,
    )
    ir_short["weather"] = weather
    ir_long["weather"]  = weather
    if intent is not None:
        ir_short["intent_id"] = intent.id
        ir_long["intent_id"]  = intent.id
    return ir_short, ir_long


def generate(
    *,
    date_iso: str,
    city_id: str,
    weather: dict,
    target_sec: float = 60.0,
    avoid_genres: list[str] | None = None,
    avoid_motifs: list[str] | None = None,
    preferred_genre: str | None = None,
    intent: Intent | None = None,
    seed_salt: str = "",
    generator_ver: str = GENERATOR_VER,
) -> dict:
    """Single-variant convenience wrapper used by the offline CLI."""
    short, _ = generate_pair(
        date_iso=date_iso, city_id=city_id, weather=weather,
        short_sec=target_sec, long_sec=target_sec * 2.2,
        avoid_genres=avoid_genres, avoid_motifs=avoid_motifs,
        preferred_genre=preferred_genre, intent=intent,
        seed_salt=seed_salt, generator_ver=generator_ver,
    )
    return short
