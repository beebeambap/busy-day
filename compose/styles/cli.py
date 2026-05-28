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


def run_style_arrangement(sb: Supabase, source_id: str,
                          style: str | None = None,
                          variant: str | None = None) -> dict:
    """Core single-song arrangement. Returns dict:
      {status: "created"|"skipped"|"failed",
       reason: <human str>,
       preset_id: <str|None>,
       variant_id: <str|None>,
       song_id: <uuid|None>}

    Used by cmd_styles (CLI) and styles_batch (loop)."""
    src = _fetch_song(sb, source_id)

    if src.get("pin_type") == "worst":
        return {"status": "skipped", "reason": "worst-pinned",
                "preset_id": None, "variant_id": None, "song_id": None}
    if src.get("tape_id"):
        return {"status": "skipped",
                "reason": f"already an arrangement (tape_id={src['tape_id']})",
                "preset_id": None, "variant_id": None, "song_id": None}
    paths_src = src.get("paths") or {}
    if not paths_src.get("ir_short") or not paths_src.get("ir_long"):
        raise RuntimeError(
            f"source song {source_id} has no IR paths (paths={paths_src})"
        )

    # Download source IR EARLY (small JSON read) so we can use the
    # source's actual sub_style for the rule's conflict-avoidance.
    # The songs table doesn't carry sub_style — it lives only in the IR
    # spec. Without this, choose_for_source treats every source as
    # sub_style=None and may pick a preset whose sub_style matches the
    # source's actual sub_style, producing a nearly-identical arrangement.
    ir_short_src = json.loads(sb.get_file(paths_src["ir_short"]).decode("utf-8"))
    source_sub_style = ir_short_src.get("spec", {}).get("sub_style")

    if style:
        preset = STYLE_PRESETS.get(style)
        if preset is None:
            raise SystemExit(
                f"unknown style preset: {style!r} "
                f"(known: {sorted(STYLE_PRESETS.keys())})"
            )
        if preset.source_genre != src["genre"]:
            raise SystemExit(
                f"preset {preset.id} requires source genre "
                f"{preset.source_genre!r}, but source is {src['genre']!r}"
            )
    else:
        pseudo_ir = {
            "spec": {"genre": src["genre"], "sub_style": source_sub_style},
            "features": (src.get("features")
                         or ir_short_src.get("features") or {}),
        }
        preset = choose_for_source(pseudo_ir)
        if preset is None:
            return {"status": "skipped",
                    "reason": f"no rule for genre {src['genre']!r}",
                    "preset_id": None, "variant_id": None, "song_id": None}

    existing = _existing_style_child(sb, source_id, preset.id)
    if existing:
        return {"status": "skipped",
                "reason": f"already arranged as {preset.id} "
                          f"(variant={existing['variant_id']})",
                "preset_id": preset.id,
                "variant_id": existing['variant_id'],
                "song_id": existing['id']}

    city    = src["city_id"]
    date    = src["date"]
    variant_id = variant or f"style-{preset.id}-{_kst_hhmm()}"

    # ── Download long IR (short already loaded above for sub_style read)
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
        "source_song_id":     source_id,
    }
    inserted = sb.upsert_row(
        "songs", row,
        on_conflict="city_id,date,generator_ver,variant_id",
    )

    return {
        "status":     "created",
        "reason":     "ok",
        "preset_id":  preset.id,
        "variant_id": variant_id,
        "song_id":    inserted.get("id"),
        # extra metadata used by the CLI summary printer
        "city": city, "date": date, "spec": spec,
        "duration_short": ir_short["duration_sec"],
        "duration_long":  ir_long["duration_sec"],
        "preset_label":   preset.label_ko,
    }


def cmd_styles(args: argparse.Namespace) -> int:
    sb = Supabase()
    r = run_style_arrangement(sb, args.source_id,
                              style=args.style, variant=args.variant)
    if r["status"] == "skipped":
        print(f"SKIP {args.source_id}: {r['reason']}")
        return 0
    if r["status"] != "created":
        print(f"FAIL {args.source_id}: {r['reason']}")
        return 1
    spec = r["spec"]
    print(
        f"\033[1m[busy-day style]\033[0m {r['date']}  {r['city']}  "
        f"variant={r['variant_id']}\n"
        f"  preset        : {r['preset_id']} ({r['preset_label']})\n"
        f"  source        : {args.source_id}\n"
        f"  spec          : {spec['key_root']} {spec['mode']} · "
        f"{spec['genre']} · {spec['bpm']} BPM · {spec['meter']} · "
        f"sub={spec.get('sub_style')}\n"
        f"  short / long  : {r['duration_short']:.1f}s / "
        f"{r['duration_long']:.1f}s\n"
        f"  storage       : busy-day-archive/{r['city']}/{r['date']}/"
        f"{r['variant_id']}/\n"
        f"  songs.id      : {r['song_id']}"
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
