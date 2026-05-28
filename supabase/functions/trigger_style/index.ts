// busy-day /trigger_style
//
// Two payloads (mode auto-detected):
//   single: POST { source_song_id, style? }
//     → dispatches style-compose with the source UUID + optional preset id.
//       returns { ok, mode: "single", variant_id, eta_sec }
//   batch:  POST { city, year, month }
//     → dispatches style-compose in batch mode for that month.
//       returns { ok, mode: "batch", eta_sec }
//
// In both flows the GitHub Actions workflow runs the Python pipeline,
// reads source IRs from Storage, applies the chosen style preset(s),
// renders new MIDI + SVG, and inserts songs row(s) with
// tape_id=<preset_id> + source_song_id linking back. The frontend
// either polls findVariant (single) or refreshes the calendar (batch).

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CITY_RE    = /^[a-z0-9_]{1,40}$/i;
const STYLE_RE   = /^[a-z0-9_]{1,40}$/i;        // preset ids like "bossa_jazz"
const VARIANT_RE = /^[a-z0-9_-]{1,60}$/i;

function j(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function kstHHMM(): string {
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  const hh = String(now.getUTCHours()).padStart(2, "0");
  const mm = String(now.getUTCMinutes()).padStart(2, "0");
  return `${hh}${mm}`;
}

async function dispatchWorkflow(inputs: Record<string, string>): Promise<Response | null> {
  const pat   = Deno.env.get("GITHUB_PAT");
  const owner = Deno.env.get("GITHUB_OWNER") ?? "beebeambap";
  const repo  = Deno.env.get("GITHUB_REPO")  ?? "busy-day";
  const wf    = Deno.env.get("GITHUB_STYLE_WORKFLOW") ?? "style-compose.yml";
  if (!pat) return j({ error: "server missing GITHUB_PAT" }, 500);

  const r = await fetch(
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
  if (!r.ok) {
    const text = await r.text();
    return j({
      error:  "github workflow_dispatch failed",
      status: r.status,
      detail: text.slice(0, 400),
    }, 502);
  }
  return null;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (req.method !== "POST")    return j({ error: "method not allowed" }, 405);

  let body: any = {};
  try { body = await req.json(); }
  catch { return j({ error: "bad json" }, 400); }

  // ── Single-song mode ────────────────────────────────────────
  const sourceId = String(body.source_song_id ?? "").trim();
  if (sourceId) {
    if (!UUID_RE.test(sourceId)) {
      return j({ error: "invalid source_song_id (expected uuid)" }, 400);
    }
    const style = String(body.style ?? "").trim();
    if (style && !STYLE_RE.test(style)) {
      return j({ error: "invalid style id" }, 400);
    }

    // Allocate variant_id here so the frontend can poll for it. When
    // style is omitted (rule-based), we don't know the preset id yet, so
    // we use a generic placeholder — the actual variant_id will be set
    // by the CLI inside the workflow. Frontend polling for "unknown"
    // variant_id is brittle; recommend the frontend just refreshes
    // calendar after ETA in that case.
    const variantId = style
      ? `style-${style}-${kstHHMM()}`
      : "";

    const inputs: Record<string, string> = { source_id: sourceId };
    if (style)     inputs.style   = style;
    if (variantId) inputs.variant = variantId;

    const err = await dispatchWorkflow(inputs);
    if (err) return err;

    return j({
      ok: true,
      mode: "single",
      variant_id: variantId,   // empty when rule-based; UI falls back to calendar refresh
      eta_sec: 45,
    });
  }

  // ── Batch (month) mode ──────────────────────────────────────
  const city  = String(body.city  ?? "").trim();
  const year  = String(body.year  ?? "").trim();
  const month = String(body.month ?? "").trim();

  if (!city || !year || !month) {
    return j({ error: "provide source_song_id (single) OR city+year+month (batch)" }, 400);
  }
  if (!CITY_RE.test(city))   return j({ error: "invalid city" }, 400);
  if (!/^\d{4}$/.test(year)) return j({ error: "invalid year (YYYY)" }, 400);
  if (!/^([1-9]|1[0-2])$/.test(month))
    return j({ error: "invalid month (1..12)" }, 400);

  const err = await dispatchWorkflow({ city, year, month });
  if (err) return err;

  return j({
    ok: true,
    mode: "batch",
    // Heuristic — a 30-song month, single-song ~45s, sequential → ~22min.
    // The actual time depends on count + GHA runner speed. Frontend should
    // refresh calendar periodically rather than block on this ETA.
    eta_sec: 60 * 22,
  });
});
