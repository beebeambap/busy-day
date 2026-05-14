// busy-day /trigger_tape
//
// POST { source_song_id, tape_id }
// -> dispatches the tape-compose GitHub Actions workflow with a
//    user-scoped variant_id, returns { variant_id, eta_sec }.
//
// Parallels /trigger but uses a different workflow and different
// inputs: tape-compose reads the source song's IR from Storage,
// applies the preset, and inserts a new songs row with tape_id and
// source_song_id set.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

// Keep in sync with compose/tapes/presets.py PRESETS keys.
const TAPE_IDS = new Set([
  "clear_hot",
  "rain",
  // planned: "cold", "snow", "fog", "storm"
]);

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

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

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (req.method !== "POST")    return j({ error: "method not allowed" }, 405);

  let body: any = {};
  try { body = await req.json(); }
  catch { return j({ error: "bad json" }, 400); }

  const sourceSongId = String(body.source_song_id ?? "").trim();
  const tapeId       = String(body.tape_id        ?? "").trim();

  if (!UUID_RE.test(sourceSongId)) {
    return j({ error: "invalid source_song_id (expected uuid)" }, 400);
  }
  if (!TAPE_IDS.has(tapeId)) {
    return j({ error: `invalid tape_id (known: ${[...TAPE_IDS].join(", ")})` }, 400);
  }

  const pat   = Deno.env.get("GITHUB_PAT");
  const owner = Deno.env.get("GITHUB_OWNER")    ?? "beebeambap";
  const repo  = Deno.env.get("GITHUB_REPO")     ?? "busy-day";
  const wf    = Deno.env.get("GITHUB_TAPE_WORKFLOW") ?? "tape-compose.yml";
  if (!pat) return j({ error: "server missing GITHUB_PAT" }, 500);

  // variant_id is allocated here (not by the workflow) so the
  // frontend can immediately start polling for the new row.
  const variantId = `tape-${tapeId}-${kstHHMM()}`;

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
      body: JSON.stringify({
        ref: "main",
        inputs: {
          source_id: sourceSongId,
          tape:      tapeId,
          variant:   variantId,
        },
      }),
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

  // Tape jobs skip the KMA fetch + compose step, so they finish
  // faster than the regular trigger (~30-45s vs ~60-90s).
  return j({ variant_id: variantId, eta_sec: 45 });
});
