"""Supabase upload: storage PUT + songs/motif_pool/weekly_theme inserts.

Uses the service-role key (write access). Never ship this key to the
browser. In production it lives in:
  - GitHub Actions secrets   (for cron + dispatch jobs)
  - Supabase edge function env (for the manual /trigger function)

The supabase project's REST endpoint is at <SUPABASE_URL>/rest/v1/...
and storage at <SUPABASE_URL>/storage/v1/object/<bucket>/<path>.
"""

from __future__ import annotations

import json
import mimetypes
import os
from typing import Any

import requests

CONTENT_TYPES = {
    ".mid":      "audio/midi",
    ".midi":     "audio/midi",
    ".json":     "application/json",
    ".svg":      "image/svg+xml",
    ".musicxml": "application/vnd.recordare.musicxml+xml",
    ".abc":      "text/plain",
}


class Supabase:
    def __init__(
        self,
        *,
        url: str | None = None,
        service_key: str | None = None,
        bucket: str | None = None,
    ):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.key = service_key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self.bucket = bucket or os.environ.get(
            "SUPABASE_STORAGE_BUCKET", "busy-day-archive"
        )

    @property
    def _hdr(self) -> dict[str, str]:
        return {
            "apikey":        self.key,
            "Authorization": f"Bearer {self.key}",
        }

    # ── storage ────────────────────────────────────────────────────
    def put_file(self, key: str, body: bytes, *, content_type: str | None = None,
                 upsert: bool = True) -> str:
        ct = content_type or CONTENT_TYPES.get(
            os.path.splitext(key)[1].lower(), "application/octet-stream"
        )
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{key}"
        headers = {**self._hdr, "Content-Type": ct, "x-upsert": str(upsert).lower()}
        r = requests.post(endpoint, data=body, headers=headers, timeout=30)
        if r.status_code >= 300:
            raise RuntimeError(f"storage put {key} failed: "
                               f"{r.status_code} {r.text}")
        return key

    def put_local(self, key: str, local_path: str, **kw) -> str:
        with open(local_path, "rb") as fh:
            return self.put_file(key, fh.read(), **kw)

    def get_file(self, key: str) -> bytes:
        """Download a file from the Storage bucket. Used by the tape
        pipeline to read the source song's IR JSON before transforming.
        The bucket is public-read, but we use the authenticated path
        anyway so private buckets work without code changes."""
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{key}"
        r = requests.get(endpoint, headers=self._hdr, timeout=30)
        if r.status_code >= 300:
            raise RuntimeError(
                f"storage get {key} failed: {r.status_code} {r.text}"
            )
        return r.content

    # ── postgrest ──────────────────────────────────────────────────
    def upsert_row(self, table: str, row: dict, *,
                   on_conflict: str | None = None) -> dict:
        endpoint = f"{self.url}/rest/v1/{table}"
        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
        headers = {
            **self._hdr,
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        }
        r = requests.post(
            endpoint, params=params, headers=headers,
            data=json.dumps(row), timeout=20,
        )
        if r.status_code >= 300:
            raise RuntimeError(
                f"upsert {table} failed: {r.status_code} {r.text}"
            )
        return r.json()[0] if r.json() else {}

    def select(self, table: str, *, params: dict[str, Any] | None = None
               ) -> list[dict]:
        endpoint = f"{self.url}/rest/v1/{table}"
        r = requests.get(endpoint, headers=self._hdr,
                         params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()


def storage_path(city_id: str, date_iso: str, basename: str,
                 variant_id: str = "auto") -> str:
    y, m, _d = date_iso.split("-")
    return f"{city_id}/{y}/{m}/{date_iso}/{variant_id}/{basename}"
