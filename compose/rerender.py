"""Re-render already-published songs from their stored IR.

Use case: a render-side change (acoustic salt, harmony-pedal removal,
thick-patch velocity scaling, …) needs to reach songs that were already
generated and released. We must NOT re-compose — that would change the
notes (melody.py / mapping.py have evolved) and the song would no longer
be "the same song". Instead we download the stored ir_short/ir_long JSON
(the frozen composition) and run the CURRENT render_midi / render_svg on
it, then overwrite the MIDI + SVG in Storage.

What this refreshes (render-side only):
  - acoustic salt: per-song detune + tempo jitter (anti-fingerprint)
  - harmony sustain-pedal removal + thick-patch velocity scaling
  - any future render.py change

What it preserves:
  - every note (pitch, timing, duration, velocity in the IR)
  - the song's DB row identity

Usage:
  python -m compose rerender --city seoul --date 2026-05-18
  python -m compose rerender --city seoul --from 2026-05-15 --to 2026-05-21
  python -m compose rerender --city seoul --date 2026-05-18 --variant auto
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile

from .arrange import write_ir
from .render import render_midi
from .score import render_svg
from .upload import Supabase, storage_path


def _songs_in_range(sb: Supabase, city: str, date_from: str,
                    date_to: str, variant: str | None) -> list[dict]:
    params = {
        "select": "id,city_id,date,variant_id,paths",
        "city_id": f"eq.{city}",
        "date": f"gte.{date_from}",
        "order": "date.asc",
    }
    rows = sb.select("songs", params=params)
    # The upper bound and variant are filtered client-side (a dict can't
    # carry two filters on the same `date` key for PostgREST).
    out = []
    for r in rows:
        if r["date"] > date_to:
            continue
        if variant and r["variant_id"] != variant:
            continue
        out.append(r)
    return out


def cmd_rerender(args: argparse.Namespace) -> int:
    sb = Supabase()
    date_from = args.date or args.date_from
    date_to = args.date or args.date_to
    if not date_from or not date_to:
        raise SystemExit("provide --date, or both --from and --to")

    songs = _songs_in_range(sb, args.city, date_from, date_to, args.variant)
    if not songs:
        print(f"no songs for {args.city} {date_from}..{date_to}"
              + (f" variant={args.variant}" if args.variant else ""))
        return 0

    print(f"re-rendering {len(songs)} song(s)…")
    done = 0
    for s in songs:
        city = s["city_id"]
        date = s["date"]
        variant = s["variant_id"]
        paths = s.get("paths") or {}
        if not paths.get("ir_short") or not paths.get("ir_long"):
            print(f"  SKIP {date}/{variant}: no IR stored")
            continue

        ir_short = json.loads(sb.get_file(paths["ir_short"]).decode("utf-8"))
        ir_long  = json.loads(sb.get_file(paths["ir_long"]).decode("utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            mid_short = os.path.join(tmp, "audio_short.mid")
            mid_long  = os.path.join(tmp, "audio_long.mid")
            svg_path  = os.path.join(tmp, "score.svg")

            # Re-render from the frozen IR with the CURRENT render code.
            render_midi(ir_short, mid_short)
            render_midi(ir_long,  mid_long)
            with open(svg_path, "w", encoding="utf-8") as fh:
                fh.write(render_svg(ir_short))

            # Overwrite the existing Storage keys (same paths → same URLs).
            mid_short_key = paths.get("mid_short") or storage_path(
                city, date, "audio_short.mid", variant)
            mid_long_key  = paths.get("mid_long") or storage_path(
                city, date, "audio_long.mid", variant)
            svg_key       = paths.get("svg") or storage_path(
                city, date, "score.svg", variant)

            sb.put_local(mid_short_key, mid_short)
            sb.put_local(mid_long_key,  mid_long)
            sb.put_local(svg_key, svg_path, content_type="image/svg+xml")

        done += 1
        print(f"  OK {date}/{variant}")

    print(f"done: {done}/{len(songs)} re-rendered")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "rerender",
        help="re-render published songs from stored IR (render-side fixes "
             "only; notes preserved)",
    )
    p.add_argument("--city", default="seoul")
    p.add_argument("--date", help="single date YYYY-MM-DD")
    p.add_argument("--from", dest="date_from", help="range start YYYY-MM-DD")
    p.add_argument("--to",   dest="date_to",   help="range end YYYY-MM-DD")
    p.add_argument("--variant", help="only this variant_id (e.g. 'auto')")
    p.set_defaults(func=cmd_rerender)
