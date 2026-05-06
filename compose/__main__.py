"""CLI:

  python -m compose generate --date YYYY-MM-DD --city seoul \\
      [--preset NAME | --weather PATH] [--out DIR]

Generates IR + MIDI for both short (~60s) and long (~130s) variants,
plus a single SVG score (rendered from the short IR; long IR is the
same melody extended).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .arrange import write_ir
from .pipeline import generate_pair
from .render import render_midi
from .score import render_svg


SAMPLE_WEATHER = {
    "seoul-mild-clear": {
        "temp_c": 18.0, "temp_range": 9.0, "humidity": 55.0,
        "precip_mm": 0.0, "wind_mps": 2.0, "cloud_pct": 20.0,
        "precip_type": "none",
    },
    "seoul-rainy-cool": {
        "temp_c": 12.0, "temp_range": 4.0, "humidity": 88.0,
        "precip_mm": 6.5, "wind_mps": 3.5, "cloud_pct": 95.0,
        "precip_type": "rain",
    },
    "seoul-warm-humid": {
        "temp_c": 27.0, "temp_range": 6.0, "humidity": 80.0,
        "precip_mm": 0.5, "wind_mps": 1.5, "cloud_pct": 60.0,
        "precip_type": "none",
    },
    "seoul-cold-clear": {
        "temp_c": -2.0, "temp_range": 11.0, "humidity": 40.0,
        "precip_mm": 0.0, "wind_mps": 4.0, "cloud_pct": 10.0,
        "precip_type": "none",
    },
}


def cmd_generate(args: argparse.Namespace) -> int:
    if args.weather:
        with open(args.weather, encoding="utf-8") as fh:
            weather = json.load(fh)
    elif args.preset:
        weather = SAMPLE_WEATHER[args.preset]
    else:
        weather = SAMPLE_WEATHER["seoul-mild-clear"]

    ir_short, ir_long = generate_pair(
        date_iso=args.date,
        city_id=args.city,
        weather=weather,
        preferred_genre=args.genre,
    )

    os.makedirs(args.out, exist_ok=True)
    paths = {
        "ir_short":  os.path.join(args.out, "ir_short.json"),
        "ir_long":   os.path.join(args.out, "ir_long.json"),
        "mid_short": os.path.join(args.out, "audio_short.mid"),
        "mid_long":  os.path.join(args.out, "audio_long.mid"),
        "svg":       os.path.join(args.out, "score.svg"),
    }

    write_ir(ir_short, paths["ir_short"])
    write_ir(ir_long,  paths["ir_long"])
    render_midi(ir_short, paths["mid_short"])
    render_midi(ir_long,  paths["mid_long"])

    svg = render_svg(ir_short)
    with open(paths["svg"], "w", encoding="utf-8") as fh:
        fh.write(svg)

    spec = ir_short["spec"]
    print(
        f"\033[1m[busy-day]\033[0m {ir_short['meta']['date']}  "
        f"{ir_short['meta']['city_id']}\n"
        f"  key/mode      : {spec['key_root']} {spec['mode']}\n"
        f"  genre         : {spec['genre']}\n"
        f"  bpm / meter   : {spec['bpm']} / {spec['meter']}\n"
        f"  motif         : {spec['motif_id']}\n"
        f"  signature     : {ir_short['signature']}\n"
        f"  start_pitch   : {ir_short['start_pitch']}\n"
        f"  short / long  : {ir_short['duration_sec']}s "
        f"({ir_short['total_bars']} bars) / "
        f"{ir_long['duration_sec']}s ({ir_long['total_bars']} bars)\n"
        f"\nwrote:\n  " + "\n  ".join(paths.values())
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="compose")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate one song (offline)")
    g.add_argument("--date", required=True, help="YYYY-MM-DD")
    g.add_argument("--city", default="seoul")
    g.add_argument("--out",  default="./out")
    g.add_argument("--weather", help="path to weather JSON")
    g.add_argument("--preset", choices=list(SAMPLE_WEATHER.keys()),
                   help="bundled weather preset for testing")
    g.add_argument("--genre", help="bias toward this genre")
    g.set_defaults(func=cmd_generate)

    # `daily` is wired in compose/daily.py and adds end-to-end (KMA + upload)
    try:
        from .daily import register as register_daily
        register_daily(sub)
    except Exception:
        pass

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
