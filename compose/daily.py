"""End-to-end daily pipeline:

  1. Fetch KMA forecast for (city, date)
  2. Pull recent signatures/motif/genre from songs table to feed the
     anti-repetition memory
  3. Compose short + long IRs, render MIDI + SVG
  4. Upload all assets to Supabase Storage
  5. Insert songs row (and ensure motif_pool / weekly_theme rows exist)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile

from . import GENERATOR_VER
from .arrange import write_ir
from .kma import KST, fetch_daily
from .pipeline import generate_pair
from .render import render_midi
from .score import render_svg
from .upload import Supabase, storage_path


def _seed_motif_pool(sb: Supabase, motifs_path: str) -> None:
    """Idempotent: ensure each seed motif exists in motif_pool."""
    with open(motifs_path, encoding="utf-8") as fh:
        motifs = json.load(fh)
    for m in motifs:
        sb.upsert_row("motif_pool", {
            "id":         m["id"],
            "added_week": m["added_week"],
            "source":     m["source"],
            "contour":    m["contour"],
            "tags":       m.get("tags", []),
            "active":     True,
        }, on_conflict="id")


def _ensure_weekly_theme(sb: Supabase, iso_week: str, genre: str) -> None:
    sb.upsert_row("weekly_theme", {
        "iso_week":        iso_week,
        "preferred_genre": genre,
        "palette":         {"v": 1},
    }, on_conflict="iso_week")


def _recent_signatures(sb: Supabase, city_id: str, date_iso: str,
                       lookback_days: int = 30) -> dict:
    today = dt.date.fromisoformat(date_iso)
    cutoff = (today - dt.timedelta(days=lookback_days)).isoformat()
    rows = sb.select("songs", params={
        "select":  "date,signature,motif_id,genre",
        "city_id": f"eq.{city_id}",
        "date":    f"gte.{cutoff}",
        "order":   "date.desc",
    })
    avoid_motifs: list[str] = []
    avoid_genres: list[str] = []
    sigs: set[str] = set()
    for row in rows:
        days = (today - dt.date.fromisoformat(row["date"])).days
        sigs.add(row["signature"])
        if days <= 7:
            avoid_motifs.append(row["motif_id"])
        if days <= 2:
            avoid_genres.append(row["genre"])
    return {
        "signatures":   sigs,
        "avoid_motifs": list(set(avoid_motifs)),
        "avoid_genres": list(set(avoid_genres)),
    }


def _city_grid(sb: Supabase, city_id: str) -> tuple[int, int]:
    rows = sb.select("cities", params={
        "select": "kma_nx,kma_ny",
        "id": f"eq.{city_id}",
    })
    if not rows or rows[0]["kma_nx"] is None:
        raise RuntimeError(f"city {city_id} has no KMA grid")
    return int(rows[0]["kma_nx"]), int(rows[0]["kma_ny"])


def cmd_daily(args: argparse.Namespace) -> int:
    from .intent import get as get_intent

    sb = Supabase()
    motifs_path = os.path.join(os.path.dirname(__file__), "data", "motifs.json")
    _seed_motif_pool(sb, motifs_path)

    city = args.city
    if args.date == "today":
        date_iso = dt.datetime.now(KST).date().isoformat()
    else:
        date_iso = args.date

    variant_id = (args.variant or "auto").strip() or "auto"
    intent = get_intent(args.intent)
    intent_id = intent.id if intent else None

    nx, ny = _city_grid(sb, city)

    # 1. weather
    if args.weather:
        with open(args.weather, encoding="utf-8") as fh:
            weather = json.load(fh)
    else:
        weather = fetch_daily(nx=nx, ny=ny, date_iso=date_iso)

    # 2. anti-repetition memory
    memory = _recent_signatures(sb, city, date_iso)

    # 3. weekly theme (resolve before song so the FK satisfies)
    today = dt.date.fromisoformat(date_iso)
    iso_year, iso_week, _ = today.isocalendar()
    iso_week_key = f"{iso_year}-W{iso_week:02d}"

    # User-triggered variants get a salt so they pick *different* mode/key
    # /motif than the day's auto song, even though the underlying date
    # seed is the same.
    seed_salt = "" if variant_id == "auto" else f"v:{variant_id}|"

    # 4. compose with retries on signature collision (max 3)
    avoid_motifs = list(memory["avoid_motifs"])
    for attempt in range(3):
        ir_short, ir_long = generate_pair(
            date_iso=date_iso, city_id=city, weather=weather,
            avoid_genres=memory["avoid_genres"],
            avoid_motifs=avoid_motifs,
            intent=intent,
            seed_salt=seed_salt + ("retry:%d|" % attempt if attempt else ""),
        )
        if ir_short["signature"] not in memory["signatures"]:
            break
        avoid_motifs = list(set(avoid_motifs + [ir_short["spec"]["motif_id"]]))

    _ensure_weekly_theme(sb, iso_week_key, ir_short["spec"]["genre"])

    # 5. render
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

        # 6. upload (paths now scoped under variant)
        keys = {
            "ir_short":  storage_path(city, date_iso, "ir_short.json",   variant_id),
            "ir_long":   storage_path(city, date_iso, "ir_long.json",    variant_id),
            "mid_short": storage_path(city, date_iso, "audio_short.mid", variant_id),
            "mid_long":  storage_path(city, date_iso, "audio_long.mid",  variant_id),
            "svg":       storage_path(city, date_iso, "score.svg",       variant_id),
        }
        sb.put_local(keys["ir_short"],  ir_short_path)
        sb.put_local(keys["ir_long"],   ir_long_path)
        sb.put_local(keys["mid_short"], mid_short_path)
        sb.put_local(keys["mid_long"],  mid_long_path)
        sb.put_local(keys["svg"],       svg_path,
                     content_type="image/svg+xml")

    # 7. insert songs row
    spec = ir_short["spec"]
    row = {
        "city_id":            city,
        "date":               date_iso,
        "variant_id":         variant_id,
        "intent_id":          intent_id,
        "seed":               ir_short["meta"]["seed"],
        "key_root":           spec["key_root"],
        "mode":               spec["mode"],
        "genre":              spec["genre"],
        "bpm":                spec["bpm"],
        "meter":              spec["meter"],
        "duration_short_sec": int(round(ir_short["duration_sec"])),
        "duration_long_sec":  int(round(ir_long["duration_sec"])),
        "weather":            weather,
        "features":           ir_short["features"],
        "signature":          ir_short["signature"],
        "start_pitch":        ir_short["start_pitch"],
        "motif_id":           spec["motif_id"],
        "week_theme":         iso_week_key,
        "paths":              keys,
        "generator_ver":      GENERATOR_VER,
    }
    inserted = sb.upsert_row(
        "songs", row,
        on_conflict="city_id,date,generator_ver,variant_id",
    )

    print(
        f"\033[1m[busy-day]\033[0m {date_iso}  {city}  variant={variant_id}"
        + (f"  intent={intent_id}" if intent_id else "") + "\n"
        f"  weather       : {weather['temp_c']}°C  "
        f"{weather['precip_type']}  {weather['humidity']}% RH\n"
        f"  spec          : {spec['key_root']} {spec['mode']} · "
        f"{spec['genre']} · {spec['bpm']} BPM · {spec['meter']}\n"
        f"  motif         : {spec['motif_id']}\n"
        f"  signature     : {ir_short['signature']}\n"
        f"  short / long  : {ir_short['duration_sec']:.1f}s / "
        f"{ir_long['duration_sec']:.1f}s\n"
        f"  storage       : busy-day-archive/{city}/{date_iso}/{variant_id}/\n"
        f"  songs.id      : {inserted.get('id')}"
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("daily", help="end-to-end (KMA + render + upload)")
    p.add_argument("--date", default="today", help="YYYY-MM-DD or 'today'")
    p.add_argument("--city", default="seoul")
    p.add_argument("--weather", help="bypass KMA, read this JSON")
    p.add_argument("--variant", default="auto",
                   help="variant id; cron uses 'auto', user uses "
                        "'user-HHMM-<intent>'")
    p.add_argument("--intent",
                   help="intent preset id (calm/warm/wistful/lively/"
                        "after_rain/sleep)")
    p.set_defaults(func=cmd_daily)
