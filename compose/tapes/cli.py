"""End-to-end CLI for tape arrangements:

  python -m compose tape \\
      --source-id <uuid> \\
      --tape <preset_id> \\
      --variant <variant_id>

Steps:
  1. Look up the source song row (city, date, paths)
  2. Download both ir_short.json and ir_long.json from Storage
  3. Apply transform_ir with the chosen preset (seeded RNG)
  4. Render new MIDI (short+long) and SVG
  5. Upload to Storage under the new variant subdirectory
  6. Insert a new songs row with tape_id + source_song_id set

The variant_id is allocated by the caller (Edge Function), so the
GHA workflow can run idempotently and the frontend polling sees a
deterministic path. variant_id pattern: "tape-<preset>-HHMM".
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile

from random import Random

from .. import GENERATOR_VER
from ..arrange import write_ir
from ..render import render_midi
from ..score import render_svg
from ..upload import Supabase, storage_path
from .presets import PRESETS, get as get_preset
from .transform import transform_ir


def _fetch_song(sb: Supabase, source_song_id: str) -> dict:
    rows = sb.select("songs", params={
        "select": "id,city_id,date,variant_id,paths,weather,features,seed,"
                  "key_root,mode,genre,bpm,meter,motif_id,signature,"
                  "start_pitch,week_theme,tape_id,instrument_id",
        "id":     f"eq.{source_song_id}",
    })
    if not rows:
        raise RuntimeError(f"source song not found: {source_song_id}")
    return rows[0]


def _seed_for_tape(source_seed: int, preset_id: str, variant_id: str) -> int:
    """Salt the source seed with the preset so the same source +
    same preset on the same minute produces the same tape (idempotent),
    while different presets produce different RNG state."""
    import hashlib
    s = f"{source_seed}|tape:{preset_id}|{variant_id}".encode()
    h = hashlib.sha256(s).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


def cmd_tape(args: argparse.Namespace) -> int:
    preset = get_preset(args.tape)
    if preset is None:
        raise SystemExit(
            f"unknown tape preset: {args.tape!r} "
            f"(known: {sorted(PRESETS.keys())})"
        )

    sb = Supabase()
    src = _fetch_song(sb, args.source_id)
    city    = src["city_id"]
    date    = src["date"]
    paths_src = src.get("paths") or {}
    if not paths_src.get("ir_short") or not paths_src.get("ir_long"):
        raise RuntimeError(
            f"source song {args.source_id} has no IR paths "
            f"(paths={paths_src})"
        )

    # 1. Download source IRs
    ir_short_src = json.loads(sb.get_file(paths_src["ir_short"]).decode("utf-8"))
    ir_long_src  = json.loads(sb.get_file(paths_src["ir_long"]).decode("utf-8"))

    # 2. Apply transform (seeded RNG per preset)
    seed = _seed_for_tape(src["seed"], preset.id, args.variant)
    rng_short = Random(seed)
    rng_long  = Random(seed ^ 0x5A5A5A5A)   # different stream for long IR
    ir_short = transform_ir(ir_short_src, preset, rng_short)
    ir_long  = transform_ir(ir_long_src,  preset, rng_long)

    variant_id = args.variant
    spec = ir_short["spec"]

    # 3. Render + upload
    with tempfile.TemporaryDirectory() as tmp:
        ir_short_path  = os.path.join(tmp, "ir_short.json")
        ir_long_path   = os.path.join(tmp, "ir_long.json")
        mid_short_path = os.path.join(tmp, "audio_short.mid")
        mid_long_path  = os.path.join(tmp, "audio_long.mid")
        svg_path       = os.path.join(tmp, "score.svg")

        write_ir(ir_short, ir_short_path)
        write_ir(ir_long,  ir_long_path)
        render_midi(ir_short, mid_short_path)
        render_midi(ir_long,  mid_long_path)
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(render_svg(ir_short))

        keys = {
            "ir_short":  storage_path(city, date, "ir_short.json",   variant_id),
            "ir_long":   storage_path(city, date, "ir_long.json",    variant_id),
            "mid_short": storage_path(city, date, "audio_short.mid", variant_id),
            "mid_long":  storage_path(city, date, "audio_long.mid",  variant_id),
            "svg":       storage_path(city, date, "score.svg",       variant_id),
        }
        sb.put_local(keys["ir_short"],  ir_short_path)
        sb.put_local(keys["ir_long"],   ir_long_path)
        sb.put_local(keys["mid_short"], mid_short_path)
        sb.put_local(keys["mid_long"],  mid_long_path)
        sb.put_local(keys["svg"],       svg_path, content_type="image/svg+xml")

    # 4. Insert the tape row. We reuse the source's week_theme / motif_id
    #    so the FKs stay valid; weather + features are also copied (the
    #    tape variant happens on the same day, so the weather context is
    #    identical).
    row = {
        "city_id":            city,
        "date":               date,
        "variant_id":         variant_id,
        "instrument_id":      preset.melody_instrument,   # tape forces melody timbre
        "seed":               seed,
        "key_root":           spec["key_root"],
        "mode":               spec["mode"],
        "genre":              spec["genre"],
        "bpm":                spec["bpm"],
        "meter":              spec["meter"],
        "duration_short_sec": int(round(ir_short["duration_sec"])),
        "duration_long_sec":  int(round(ir_long["duration_sec"])),
        "weather":            src.get("weather") or {},
        "features":           src.get("features") or ir_short.get("features", {}),
        "signature":          ir_short["signature"],
        "start_pitch":        ir_short.get("start_pitch") or src["start_pitch"],
        "motif_id":           src["motif_id"],
        "week_theme":         src["week_theme"],
        "paths":              keys,
        "generator_ver":      GENERATOR_VER,
        "tape_id":            preset.id,
        "source_song_id":     args.source_id,
    }
    inserted = sb.upsert_row(
        "songs", row,
        on_conflict="city_id,date,generator_ver,variant_id",
    )

    print(
        f"\033[1m[busy-day tape]\033[0m {date}  {city}  variant={variant_id}\n"
        f"  preset        : {preset.id} ({preset.label_ko})\n"
        f"  source        : {args.source_id}\n"
        f"  spec          : {spec['key_root']} {spec['mode']} · "
        f"{spec['genre']} · {spec['bpm']} BPM · {spec['meter']} · "
        f"voicing={spec.get('voicing')}\n"
        f"  short / long  : {ir_short['duration_sec']:.1f}s / "
        f"{ir_long['duration_sec']:.1f}s\n"
        f"  storage       : busy-day-archive/{city}/{date}/{variant_id}/\n"
        f"  songs.id      : {inserted.get('id')}"
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "tape",
        help="apply a weather tape preset to an existing song "
             "(read source IR from Storage, transform, render, upload)",
    )
    p.add_argument("--source-id", dest="source_id", required=True,
                   help="UUID of the source song to re-arrange")
    p.add_argument("--tape", required=True,
                   choices=sorted(PRESETS.keys()),
                   help="tape preset id")
    p.add_argument("--variant", required=True,
                   help="variant id for the new song row "
                        "(e.g. 'tape-clear_hot-HHMM')")
    p.set_defaults(func=cmd_tape)
