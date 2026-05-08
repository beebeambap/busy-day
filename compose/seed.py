"""Deterministic seed derivation.

The seed is purely a function of (date, city, generator_ver). Reproducing
the same song on a different day means feeding the same triple back in.
"""

from __future__ import annotations

import hashlib
import random


def make_seed(date_iso: str, city_id: str, generator_ver: str) -> int:
    raw = f"{date_iso}|{city_id}|{generator_ver}".encode()
    digest = hashlib.sha256(raw).digest()
    # Mask to 63 bits so the value always fits in PostgreSQL's signed
    # bigint column. We accept that ~half of all dates lose one bit of
    # entropy; a 63-bit space is still 9.2 × 10^18, more than enough
    # for an unbounded date range.
    return int.from_bytes(digest[:8], "big", signed=False) & ((1 << 63) - 1)


def rng(seed: int, salt: str = "") -> random.Random:
    if salt:
        seed = int.from_bytes(
            hashlib.sha256(f"{seed}:{salt}".encode()).digest()[:8], "big"
        )
    return random.Random(seed)
