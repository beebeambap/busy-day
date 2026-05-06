"""End-to-end orchestration for one (date, city) song."""

from __future__ import annotations

from random import Random
from typing import Any

from . import GENERATOR_VER
from .arrange import compose_ir
from .features import extract
from .mapping import (
    pick_bpm,
    pick_genre,
    pick_key,
    pick_meter,
    pick_mode,
    pick_motif,
)
from .seed import make_seed, rng


def _decide_spec(
    seed: int,
    features,
    *,
    avoid_genres: list[str] | None,
    avoid_motifs: list[str] | None,
    preferred_genre: str | None,
) -> dict:
    mode  = pick_mode(rng(seed, "main"), features)
    key   = pick_key(rng(seed, "key"), features)
    genre = pick_genre(
        rng(seed, "genre"), features,
        avoid=avoid_genres, preferred=preferred_genre,
    )
    bpm   = pick_bpm(rng(seed, "bpm"), features, genre)
    meter = pick_meter(rng(seed, "meter"), genre)
    motif = pick_motif(
        rng(seed, "motif"), features,
        avoid_ids=set(avoid_motifs or []),
    )
    return {
        "key_root": key, "mode": mode, "genre": genre,
        "bpm": bpm, "meter": meter, "motif": motif,
    }


def generate(
    *,
    date_iso: str,
    city_id: str,
    weather: dict,
    target_sec: float = 60.0,
    avoid_genres: list[str] | None = None,
    avoid_motifs: list[str] | None = None,
    preferred_genre: str | None = None,
    generator_ver: str = GENERATOR_VER,
) -> dict:
    """Single-variant convenience wrapper. See `generate_pair` for both
    short + long."""
    seed = make_seed(date_iso, city_id, generator_ver)
    features = extract(weather)
    spec = _decide_spec(
        seed, features,
        avoid_genres=avoid_genres,
        avoid_motifs=avoid_motifs,
        preferred_genre=preferred_genre,
    )
    ir = compose_ir(
        date_iso=date_iso,
        city_id=city_id,
        seed=seed,
        rng=rng(seed, f"compose:{int(target_sec)}"),
        features=features,
        spec=spec,
        target_sec=target_sec,
    )
    ir["weather"] = weather
    return ir


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
    generator_ver: str = GENERATOR_VER,
) -> tuple[dict, dict]:
    """Generate the short and long variants of the same song.

    Both share the (key, mode, genre, bpm, meter, motif) spec; only the
    form expands. The long variant is a natural extension, not a remix.
    """
    seed = make_seed(date_iso, city_id, generator_ver)
    features = extract(weather)
    spec = _decide_spec(
        seed, features,
        avoid_genres=avoid_genres,
        avoid_motifs=avoid_motifs,
        preferred_genre=preferred_genre,
    )
    ir_short = compose_ir(
        date_iso=date_iso, city_id=city_id, seed=seed,
        rng=rng(seed, "compose:short"),
        features=features, spec=spec, target_sec=short_sec,
    )
    ir_long = compose_ir(
        date_iso=date_iso, city_id=city_id, seed=seed,
        rng=rng(seed, "compose:long"),
        features=features, spec=spec, target_sec=long_sec,
    )
    ir_short["weather"] = weather
    ir_long["weather"]  = weather
    return ir_short, ir_long
