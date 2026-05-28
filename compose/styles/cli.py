"""End-to-end CLI for genre-style arrangements.

  python -m compose styles \\
      --source-id <uuid> \\
      [--style <preset_id>]      # default: rule-based auto-pick
      [--variant <variant_id>]   # default: style-<preset>-HHMM

Steps (parallel to compose/tapes/cli.py):
  1. Fetch source song row (city, date, paths, features, sub_style)
  2. Validate: not a worst-pinned song, not itself an arrangement,
     not already arranged with the same preset
  3. Download ir_short.json + ir_long.json from Storage
  4. Choose preset (rule-based) or use --style override
  5. Apply transform_ir with chosen preset (seeded RNG)
  6. Render new MIDI (short+long) + SVG
  7. Upload to Storage under the new variant subdirectory
  8. Insert a new songs row with tape_id=<preset_id> + source_song_id

tape_id column is reused — both weather tape and genre style
arrangements live under the same parent-child model. variant_id
prefix ("style-" vs "tape-") distinguishes them in URLs/UI.
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
from ..tapes.transform import transform_ir
from ..upload import Supabase, storage_path
from .presets import STYLE_PRESETS, choose_for_source


def _kst_hhmm() -> str:
    kst = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime.now(kst)
    return now.strftime("%H%M")


def _fetch_song(sb: Supabase, source_song_id: str) -> dict:
    rows = sb.select("songs", params={
        "select": "id,city_id,date,variant_id,paths,weather,features,seed,"
                  "key_root,mode,genre,bpm,meter,motif_id,signature,"
                  "start_pitch,week_theme,tape_id,instrument_id,pin_type,"
                  "source_song_id",
        "id":     f"eq.{source_song_id}",
    })
    if not rows:
        raise RuntimeError(f"source song not found: {source_song_id}")
    return rows[0]


def _existing_style_child(sb: Supabase, source_song_id: str,
                          preset_id: str) -> dict | None:
    """Return the existing style arrangement of this source with this
    preset, or None. Used for idempotent dispatch: re-running the same
    style on the same source returns the existing row instead of
    creating a duplicate."""
    rows = sb.select("songs", params={
        "select":          "id,variant_id,date,paths",
        "source_song_id":  f"eq.{source_song_id}",
        "tape_id":         f"eq.{preset_id}",
        "limit":           "1",
    })
    return rows[0] if rows else None


def _seed_for_style(source_seed: int, preset_id: str, variant_id: str) -> int:
    """Salt source seed with style preset + variant. Same source +
    same preset + same minute = same arrangement (idempotent within a
    minute). Different variant_id (different minute) = different RNG
    state → user can re-roll for a fresh interpretation."""
    import hashlib
    s = f"{source_seed}|style:{preset_id}|{variant_id}".encode()
    h = hashlib.sha256(s).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


def cmd_styles(args: argparse.Namespace) -> int:
    sb = Supabase()
    src = _fetch_song(sb, args.source_id)

    # ── Validation ────────────────────────────────────────────────
    if src.get("pin_type") == "worst":
        print(f"SKIP {args.source_id}: source is worst-pinned")
        return 0
    if src.get("tape_id"):
        # Already an arrangement (tape or style) → don't arrange-of-arrangement
        print(f"SKIP {args.source_id}: source is itself an arrangement "
              f"(tape_id={src['tape_id']})")
        return 0
    paths_src = src.get("paths") or {}
    if not paths_src.get("ir_short") or not paths_src.get("ir_long"):
        raise RuntimeError(
            f"source song {args.source_id} has no IR paths (paths={paths_src})"
        )

    # ── Preset selection ─────────────────────────────────────────
    if args.style:
        preset = STYLE_PRESETS.get(args.style)
        if preset is None:
            raise SystemExit(
                f"unknown style preset: {args.style!r} "
                f"(known: {sorted(STYLE_PRESETS.keys())})"
            )
        if preset.source_genre != src["genre"]:
            raise SystemExit(
                f"preset {preset.id} requires source genre "
                f"{preset.source_genre!r}, but source is {src['genre']!r}"
            )
    else:
        # Rule-based auto-pick from the source's features. We need a
        # minimal IR-like dict for choose_for_source.
        pseudo_ir = {
            "spec": {
                "genre":     src["genre"],
                "sub_style": None,  # source row doesn't carry sub_style;
                                    # safest assumption — never equal to
                                    # any preset's sub_style → no conflict
            },
            "features": src.get("features") or {},
        }
        preset = choose_for_source(pseudo_ir)
        if preset is None:
            print(f"SKIP {args.source_id}: no rule for genre {src['genre']!r}")
            return 0

    # ── Idempotency: same source + same preset already exists? ─────
    existing = _existing_style_child(sb, args.source_id, preset.id)
    if existing:
        print(f"SKIP {args.source_id}: already arranged as {preset.id} "
              f"(existing variant={existing['variant_id']})")
        return 0

    city    = src["city_id"]
    date    = src["date"]
    variant_id = args.variant or f"style-{preset.id}-{_kst_hhmm()}"

    # ── Download source IRs ───────────────────────────────────────
    ir_short_src = json.loads(sb.get_file(paths_src["ir_short"]).decode("utf-8"))
    ir_long_src  = json.loads(sb.get_file(paths_src["ir_long"]).decode("utf-8"))

    # ── Transform (seeded) ────────────────────────────────────────
    seed = _seed_for_style(src["seed"], preset.id, variant_id)
    rng_short = Random(seed)
    rng_long  = Random(seed ^ 0x5A5A5A5A)
    ir_short = transform_ir(ir_short_src, preset, rng_short)
    ir_long  = transform_ir(ir_long_src,  preset, rng_long)
    spec = ir_short["spec"]

    # ── Render + upload ───────────────────────────────────────────
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

    # ── Insert songs row ──────────────────────────────────────────
    # Reuses source's week_theme/motif_id to keep FKs valid; weather +
    # features are also copied (style arrangement happens on the same
    # day as the source, so weather context is identical).
    row = {
        "city_id":            city,
        "date":               date,
        "variant_id":         variant_id,
        "instrument_id":      preset.melody_instrument,
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
        # Reuse tape_id column for style preset id — both share the
        # parent-child arrangement model. UI distinguishes by prefix.
        "tape_id":            preset.id,
        "source_song_id":     args.source_id,
    }
    inserted = sb.upsert_row(
        "songs", row,
        on_conflict="city_id,date,generator_ver,variant_id",
    )

    print(
        f"\033[1m[busy-day style]\033[0m {date}  {city}  variant={variant_id}\n"
        f"  preset        : {preset.id} ({preset.label_ko})\n"
        f"  source        : {args.source_id}\n"
        f"  spec          : {spec['key_root']} {spec['mode']} · "
        f"{spec['genre']} · {spec['bpm']} BPM · {spec['meter']} · "
        f"sub={spec.get('sub_style')}\n"
        f"  short / long  : {ir_short['duration_sec']:.1f}s / "
        f"{ir_long['duration_sec']:.1f}s\n"
        f"  storage       : busy-day-archive/{city}/{date}/{variant_id}/\n"
        f"  songs.id      : {inserted.get('id')}"
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "styles",
        help="apply a genre-style preset to an existing source song "
             "(rule-based auto-pick unless --style is given)",
    )
    p.add_argument("--source-id", dest="source_id", required=True,
                   help="UUID of the source song to re-arrange")
    p.add_argument("--style", default=None,
                   help="preset id (e.g. bossa_jazz). Omit → rule-based "
                        "auto-pick from source's features.")
    p.add_argument("--variant", default=None,
                   help="variant_id (e.g. style-bossa_jazz-1530). "
                        "Omit → auto-generated as style-<preset>-HHMM.")
    p.set_defaults(func=cmd_styles)
