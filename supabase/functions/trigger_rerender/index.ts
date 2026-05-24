// busy-day /trigger_rerender
//
// POST { city, date, variant?, to? }
// -> dispatches the rerender GitHub Actions workflow, which re-renders
//    the published song(s) from their stored IR (render-side fixes only;
//    notes preserved) and overwrites the MIDI + SVG in Storage in place.
// -> returns { ok: true, eta_sec }.
//
// Unlike /trigger and /trigger_tape, this does NOT create a new row or
// variant — it refreshes existing files. The frontend just waits the
// ETA then re-fetches the (same-URL) MIDI with a cache-bust.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const CITY_RE = /^[a-z0-9_]{1,40}$/i;
// variant ids we generate: "auto", "user-HHMM-<intent>", "tape-<id>-HHMM"
const VARIANT_RE = /^[a-z0-9_-]{1,60}$/i;

function j(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (req.method !== "POST")    return j({ error: "method not allowed" }, 405);

  let body: any = {};
  try { body = await req.json(); }
  catch { return j({ error: "bad json" }, 400); }

  const city    = String(body.city    ?? "").trim();
  const date    = String(body.date    ?? "").trim();
  const to      = String(body.to      ?? "").trim();
  const variant = String(body.variant ?? "").trim();

  if (!CITY_RE.test(city))  return j({ error: "invalid city" }, 400);
  if (!DATE_RE.test(date))  return j({ error: "invalid date (YYYY-MM-DD)" }, 400);
  if (to && !DATE_RE.test(to))
    return j({ error: "invalid 'to' (YYYY-MM-DD)" }, 400);
  if (variant && !VARIANT_RE.test(variant))
    return j({ error: "invalid variant" }, 400);

  const pat   = Deno.env.get("GITHUB_PAT");
  const owner = Deno.env.get("GITHUB_OWNER") ?? "beebeambap";
  const repo  = Deno.env.get("GITHUB_REPO")  ?? "busy-day";
  const wf    = Deno.env.get("GITHUB_RERENDER_WORKFLOW") ?? "rerender.yml";
  if (!pat) return j({ error: "server missing GITHUB_PAT" }, 500);

  const inputs: Record<string, string> = { city, date };
  if (to)      inputs.to = to;
  if (variant) inputs.variant = variant;

  const ghResp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${wf}/dispatches`,
    {
      method: "POST",
      headers: {
        "Accept":               "application/vnd.github+json",
        "Authorization":        `Bearer ${pat}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":         "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    },
  );

  if (!ghResp.ok) {
    const text = await ghResp.text();
    return j({
      error:  "github workflow_dispatch failed",
      status: ghResp.status,
      detail: text.slice(0, 400),
    }, 502);
  }

  // Single-song re-render is fast (~30-40s incl. runner spin-up). Ranges
  // take longer but the frontend only triggers single songs.
  return j({ ok: true, eta_sec: to ? 90 : 40 });
});
