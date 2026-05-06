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


def generate(
    *,
    date_iso: str,
    city_id: str,
    weather: dict,
    avoid_genres: list[str] | None = None,
    avoid_motifs: list[str] | None = None,
    preferred_genre: str | None = None,
    generator_ver: str = GENERATOR_VER,
) -> dict:
    seed = make_seed(date_iso, city_id, generator_ver)
    features = extract(weather)

    r_main = rng(seed, "main")
    mode  = pick_mode(r_main, features)
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

    spec = {
        "key_root": key,
        "mode": mode,
        "genre": genre,
        "bpm": bpm,
        "meter": meter,
        "motif": motif,
    }

    ir = compose_ir(
        date_iso=date_iso,
        city_id=city_id,
        seed=seed,
        rng=rng(seed, "compose"),
        features=features,
        spec=spec,
    )
    # weather snapshot lives in IR for traceability
    ir["weather"] = weather
    return ir
