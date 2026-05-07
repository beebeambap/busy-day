// busy-day /trigger
//
// POST { date, city?, intent_id, instrument_id?, genre_id? }
// -> dispatches the daily-compose GitHub Actions workflow with a
//    user-scoped variant_id, returns { variant_id, eta_sec }.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const INTENT_IDS = new Set([
  // emotional moods
  "calm", "warm", "wistful", "lively", "after_rain", "sleep",
  // situational moods (manual-only flow)
  "dawn", "commute", "nap", "focus", "walk",
]);
const INSTRUMENT_IDS = new Set([
  "piano", "rhodes", "nylon", "violin", "viola", "cello",
  "strings", "music_box", "horn",
]);
const GENRE_IDS = new Set([
  "ambient", "bossa_nova", "jazz_ballad", "lo_fi",
  "neo_classical", "folk",
]);

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

  const date         = String(body.date          ?? "today").slice(0, 16);
  const city         = String(body.city          ?? "seoul").slice(0, 32);
  const intentId     = String(body.intent_id     ?? "").slice(0, 32);
  const instrumentId = String(body.instrument_id ?? "").slice(0, 32);
  const genreId      = String(body.genre_id      ?? "").slice(0, 32);

  if (!INTENT_IDS.has(intentId)) return j({ error: "invalid intent_id" }, 400);
  if (instrumentId && !INSTRUMENT_IDS.has(instrumentId)) {
    return j({ error: "invalid instrument_id" }, 400);
  }
  if (genreId && !GENRE_IDS.has(genreId)) {
    return j({ error: "invalid genre_id" }, 400);
  }

  const pat   = Deno.env.get("GITHUB_PAT");
  const owner = Deno.env.get("GITHUB_OWNER")    ?? "beebeambap";
  const repo  = Deno.env.get("GITHUB_REPO")     ?? "busy-day";
  const wf    = Deno.env.get("GITHUB_WORKFLOW") ?? "daily-compose.yml";
  if (!pat) return j({ error: "server missing GITHUB_PAT" }, 500);

  const tagBits = [intentId];
  if (genreId)      tagBits.push(genreId);
  if (instrumentId) tagBits.push(instrumentId);
  const variantId = `user-${kstHHMM()}-${tagBits.join("-")}`;

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
          date, city,
          variant: variantId,
          intent: intentId,
          instrument: instrumentId,
          force_genre: genreId,
        },
      }),
    },
  );

  if (!ghResp.ok) {
    const text = await ghResp.text();
    return j({ error: "dispatch failed", status: ghResp.status, detail: text }, 502);
  }

  return j({
    variant_id:    variantId,
    intent_id:     intentId,
    instrument_id: instrumentId || null,
    genre_id:      genreId || null,
    date, city,
    eta_sec: 90,
  });
});
