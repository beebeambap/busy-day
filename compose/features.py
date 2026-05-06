"""Weather aggregate -> normalized features in [0, 1].

Inputs come from the daily KMA aggregate (see DESIGN/PIPELINE):
  temp_c, temp_range, humidity, precip_mm, wind_mps, cloud_pct, precip_type

Output is a dict of features the mapper consumes:
  warmth      = how warm it feels (temp + humidity)
  brightness  = how bright (inverse of cloud + precip)
  wetness     = precipitation level
  calmness    = inverse of wind speed and temp swing
"""

from __future__ import annotations

from dataclasses import dataclass


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Features:
    warmth: float
    brightness: float
    wetness: float
    calmness: float

    def as_dict(self) -> dict:
        return {
            "warmth": round(self.warmth, 3),
            "brightness": round(self.brightness, 3),
            "wetness": round(self.wetness, 3),
            "calmness": round(self.calmness, 3),
        }


def extract(weather: dict) -> Features:
    temp_c     = float(weather.get("temp_c", 15.0))
    temp_range = float(weather.get("temp_range", 8.0))
    humidity   = float(weather.get("humidity", 60.0))
    precip_mm  = float(weather.get("precip_mm", 0.0))
    wind_mps   = float(weather.get("wind_mps", 2.0))
    cloud_pct  = float(weather.get("cloud_pct", 50.0))

    # warmth: -10°C -> 0, 30°C -> 1; nudged up by humidity
    warmth = _clip((temp_c + 10.0) / 40.0 + (humidity - 60.0) / 200.0)

    # brightness: clear & dry & sunny = 1
    brightness = _clip(
        1.0
        - cloud_pct / 130.0
        - min(precip_mm, 20.0) / 30.0
    )

    # wetness: 0mm -> 0; 20mm -> 1
    wetness = _clip(precip_mm / 20.0 + humidity / 250.0 - 0.2)

    # calmness: low wind + small temp swing = 1
    calmness = _clip(
        1.0
        - min(wind_mps, 10.0) / 10.0
        - min(temp_range, 15.0) / 30.0
    )

    return Features(warmth, brightness, wetness, calmness)
