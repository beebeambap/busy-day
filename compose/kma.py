"""KMA (Korea Meteorological Administration) short-term forecast client.

Endpoint: getVilageFcst from VilageFcstInfoService_2.0
Docs:     data.go.kr -> 단기예보 조회 서비스

Service key is issued per developer at data.go.kr. We pass it as
KMA_SERVICE_KEY (URL-encoded once or as the raw "decoded" form — both
work but the encoded one is safer through requests).

KMA's base_time grid runs at 02, 05, 08, 11, 14, 17, 20, 23 KST.
We pull the most recent slot before "now" and aggregate the next ~24h.
"""

from __future__ import annotations

import datetime as dt
import os
import statistics
import time
from typing import Any

import requests

KST = dt.timezone(dt.timedelta(hours=9))
BASE_URL = (
    "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
)
BASE_TIMES = [200, 500, 800, 1100, 1400, 1700, 2000, 2300]

# Transient HTTP statuses worth retrying. 429 = rate limit (the cron
# failure we saw); 5xx = upstream hiccups.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BACKOFF_BASE = 2.0   # seconds: 2, 4, 8, 16


def _get_with_retry(url: str, params: dict, timeout: float) -> requests.Response:
    """GET with exponential backoff on transient errors (429 / 5xx /
    connection failures). Honors a Retry-After header when present.

    KMA's public endpoint rate-limits aggressively around the top of
    the hour (when our 06:00 KST cron and everyone else's jobs fire),
    so a single 429 used to kill the whole daily compose. Retrying with
    backoff makes the cron resilient to those bursts."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = _BACKOFF_BASE * (2 ** attempt)
                time.sleep(delay)
                continue
            return r
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
                continue
            raise
    # Exhausted retries on a retryable status — return the last response
    # so the caller's raise_for_status() surfaces the real error.
    if last_exc is not None:
        raise last_exc
    return r


def _pick_base(now_kst: dt.datetime) -> tuple[str, str]:
    """Return (base_date YYYYMMDD, base_time HHMM) with KMA's ~10-min lag rule."""
    candidate = now_kst - dt.timedelta(minutes=15)
    hhmm = candidate.hour * 100 + candidate.minute
    base_time_int = max((t for t in BASE_TIMES if t <= hhmm), default=None)
    if base_time_int is None:
        candidate = candidate - dt.timedelta(days=1)
        base_time_int = BASE_TIMES[-1]
    base_date = candidate.strftime("%Y%m%d")
    return base_date, f"{base_time_int:04d}"


def _precip_type(code: str | int) -> str:
    code = int(code)
    return {0: "none", 1: "rain", 2: "rain_snow", 3: "snow", 4: "shower"}.get(
        code, "none"
    )


def _aggregate(items: list[dict], target_date: str) -> dict:
    """Reduce hourly forecasts (a list of category-typed records) to a
    single daily summary that compose.features expects.

    KMA's short-term forecast only covers ~3 days into the future. If
    `target_date` is older than the forecast window the response will
    have no rows for it, but it *will* have rows for the days the API
    can see. In that case we fall back to the closest available date
    and flag the result with `fallback=true` so the caller knows the
    weather is approximate.
    """
    # Group raw items by fcstDate -> fcstTime -> category
    by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for it in items:
        d = it["fcstDate"]
        by_date.setdefault(d, {}) \
              .setdefault(it["fcstTime"], {})[it["category"]] = it["fcstValue"]

    if not by_date:
        raise RuntimeError("KMA returned no forecast rows at all")

    if target_date in by_date:
        used_date = target_date
        fallback = False
    else:
        # Pick whichever date in the response is numerically closest to
        # the request. For a request 3 days in the past, this picks the
        # earliest forecast day, which is the closest weather we have.
        try:
            tgt_int = int(target_date)
            used_date = min(by_date.keys(),
                            key=lambda d: abs(int(d) - tgt_int))
        except ValueError:
            used_date = sorted(by_date.keys())[0]
        fallback = True

    by_hour = by_date[used_date]
    temps = [float(h["TMP"]) for h in by_hour.values() if "TMP" in h]
    rehs  = [float(h["REH"]) for h in by_hour.values() if "REH" in h]
    wsds  = [float(h["WSD"]) for h in by_hour.values() if "WSD" in h]
    skys  = [int(h["SKY"])   for h in by_hour.values() if "SKY" in h]
    ptys  = [int(h["PTY"])   for h in by_hour.values() if "PTY" in h]

    pcps = []
    for h in by_hour.values():
        v = h.get("PCP", "강수없음")
        if v in ("강수없음", "-", None):
            pcps.append(0.0)
        else:
            try:
                # KMA returns "1.0mm", "1mm 미만", "30.0~50.0mm" etc.
                token = (
                    v.replace("mm", "").replace("미만", "")
                     .split("~")[0].strip() or "0"
                )
                pcps.append(float(token))
            except (ValueError, AttributeError):
                pcps.append(0.0)

    out = {
        "temp_c":      round(statistics.mean(temps), 1) if temps else 15.0,
        "temp_range":  round(max(temps) - min(temps), 1) if temps else 8.0,
        "humidity":    round(statistics.mean(rehs), 1) if rehs else 60.0,
        "precip_mm":   round(sum(pcps), 1),
        "wind_mps":    round(statistics.mean(wsds), 1) if wsds else 2.0,
        "cloud_pct":   round(statistics.mean(skys) / 4.0 * 100.0, 1) if skys else 50.0,
        "precip_type": _precip_type(max(ptys) if ptys else 0),
        "source":         "kma",
        "base_date":      used_date,
        "requested_date": target_date,
    }
    if fallback:
        out["fallback"] = True
        out["fallback_reason"] = (
            f"KMA forecast had no rows for {target_date}; "
            f"used closest available date {used_date}"
        )
    return out


def fetch_daily(
    *,
    nx: int,
    ny: int,
    date_iso: str,
    service_key: str | None = None,
    now: dt.datetime | None = None,
    timeout: float = 15.0,
) -> dict:
    """Fetch the daily aggregate for a city grid.

    `date_iso` is YYYY-MM-DD in KST. The function picks the most recent
    base_time before `now` (default = current KST) and pulls the
    matching forecast page(s).
    """
    service_key = service_key or os.environ.get("KMA_SERVICE_KEY", "")
    if not service_key:
        raise RuntimeError("KMA_SERVICE_KEY is not set")

    now_kst = (now or dt.datetime.now(dt.timezone.utc)).astimezone(KST)
    base_date, base_time = _pick_base(now_kst)
    target = date_iso.replace("-", "")

    rows: list[dict] = []
    page = 1
    while True:
        params = {
            "serviceKey":    service_key,
            "pageNo":        page,
            "numOfRows":     1000,
            "dataType":      "JSON",
            "base_date":     base_date,
            "base_time":     base_time,
            "nx":            nx,
            "ny":            ny,
        }
        r = _get_with_retry(BASE_URL, params, timeout)
        r.raise_for_status()
        body = r.json()
        head = body.get("response", {}).get("header", {})
        if head.get("resultCode") not in ("00", 0):
            raise RuntimeError(
                f"KMA error {head.get('resultCode')}: {head.get('resultMsg')}"
            )
        items = (
            body.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [])
        )
        rows.extend(items)
        total = int(body["response"]["body"]["totalCount"])
        if page * 1000 >= total:
            break
        page += 1

    return _aggregate(rows, target)
