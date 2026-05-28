"""Month-wide batch arrangement.

  python -m compose styles-batch --city seoul --year 2026 --month 5

Iterates eligible source songs in (city, year, month):
  - tape_id IS NULL          (originals only — no arrangement-of-arrangement)
  - pin_type != 'worst'      (user-excluded songs)
For each, runs run_style_arrangement (rule-based preset, idempotent).
Continues on per-song failure; prints summary at end.

Eligible "originals" = auto + user-* variants on dates within the month.
worst-pinned are filtered by the query; an additional defensive check
lives inside run_style_arrangement so a manual single-song call is
also safe.
"""

from __future__ import annotations

import argparse
from collections import Counter

from ..upload import Supabase
from .cli import run_style_arrangement


def _eligible_songs(sb: Supabase, city: str, year: int,
                    month: int) -> list[dict]:
    """Songs in (city, year, month) that are arrangement candidates."""
    start = f"{year:04d}-{month:02d}-01"
    nxt_y = year + (1 if month == 12 else 0)
    nxt_m = 1 if month == 12 else month + 1
    end = f"{nxt_y:04d}-{nxt_m:02d}-01"
    rows = sb.select("songs", params={
        "select":  "id,city_id,date,variant_id,genre,pin_type,tape_id",
        "city_id": f"eq.{city}",
        "date":    f"gte.{start}",
        "tape_id": "is.null",
        "order":   "date.asc,variant_id.asc",
    })
    # PostgREST dict can't carry two filters on `date`; filter upper end
    # + worst client-side.
    return [r for r in rows
            if r["date"] < end and r.get("pin_type") != "worst"]


def cmd_styles_batch(args: argparse.Namespace) -> int:
    sb = Supabase()
    songs = _eligible_songs(sb, args.city, args.year, args.month)
    print(f"[busy-day style-batch] {args.city} {args.year}-{args.month:02d}: "
          f"{len(songs)} eligible source(s)")
    if not songs:
        return 0

    summary = Counter()
    for i, s in enumerate(songs, 1):
        sid = s["id"]
        prefix = f"[{i:3d}/{len(songs)}]"
        try:
            r = run_style_arrangement(sb, sid)
        except Exception as e:
            print(f"{prefix} FAIL {s['date']}/{s['variant_id']}: {e}")
            summary["failed"] += 1
            continue
        status = r["status"]
        summary[status] += 1
        if status == "created":
            print(f"{prefix} OK   {s['date']}/{s['variant_id']} "
                  f"→ {r['preset_id']} (variant={r['variant_id']})")
        elif status == "skipped":
            print(f"{prefix} SKIP {s['date']}/{s['variant_id']}: {r['reason']}")

    print(
        f"\n[done] created={summary['created']}, "
        f"skipped={summary['skipped']}, failed={summary['failed']}"
    )
    return 0 if summary["failed"] == 0 else 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "styles-batch",
        help="apply rule-based genre-style arrangement to every eligible "
             "source song in a given month",
    )
    p.add_argument("--city", required=True, help="city id (e.g. seoul)")
    p.add_argument("--year", type=int, required=True, help="year (e.g. 2026)")
    p.add_argument("--month", type=int, required=True,
                   help="month 1..12 (calendar view's current month)")
    p.set_defaults(func=cmd_styles_batch)
