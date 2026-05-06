"""CLI: python -m compose generate --date YYYY-MM-DD --city seoul --out ./out

Phase 1 emits IR.json + audio.mid only. Audio/score rendering arrives in
phase 2.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .arrange import write_ir
from .pipeline import generate
from .render import render_midi


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

    ir = generate(
        date_iso=args.date,
        city_id=args.city,
        weather=weather,
        preferred_genre=args.genre,
    )

    os.makedirs(args.out, exist_ok=True)
    ir_path  = os.path.join(args.out, "ir.json")
    mid_path = os.path.join(args.out, "audio.mid")

    write_ir(ir, ir_path)
    render_midi(ir, mid_path)

    spec = ir["spec"]
    print(
        f"\033[1m[busy-day]\033[0m {ir['meta']['date']}  {ir['meta']['city_id']}\n"
        f"  key/mode      : {spec['key_root']} {spec['mode']}\n"
        f"  genre         : {spec['genre']}\n"
        f"  bpm / meter   : {spec['bpm']} / {spec['meter']}\n"
        f"  motif         : {spec['motif_id']}\n"
        f"  signature     : {ir['signature']}\n"
        f"  start_pitch   : {ir['start_pitch']}\n"
        f"  duration      : ~{ir['duration_short_sec']}s short / "
        f"~{ir['duration_long_sec']}s long\n"
        f"  bars / events : {ir['total_bars']} / "
        f"{len(ir['tracks']['melody'])} melody, "
        f"{len(ir['tracks']['harmony'])} harmony, "
        f"{len(ir['tracks']['bass'])} bass\n"
        f"\nwrote:\n  {ir_path}\n  {mid_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="compose")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate one song")
    g.add_argument("--date", required=True, help="YYYY-MM-DD")
    g.add_argument("--city", default="seoul")
    g.add_argument("--out",  default="./out")
    g.add_argument("--weather", help="path to weather JSON; overrides --preset")
    g.add_argument("--preset", choices=list(SAMPLE_WEATHER.keys()),
                   help="bundled weather preset for testing")
    g.add_argument("--genre", help="bias toward this genre")
    g.set_defaults(func=cmd_generate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
