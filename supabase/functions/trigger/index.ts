// busy-day /trigger
//
// POST { date, city?, intent_id }
// -> dispatches the daily-compose GitHub Actions workflow with a
//    user-scoped variant_id, returns { variant_id, eta_sec }.
//
// Auth: this function intentionally has verify_jwt=false because the
// page is gated by a client-side password (single-user app). Anonymous
// abuse would only burn the PAT's workflow_dispatch quota; rotate the
// PAT if that ever happens.
//
// Required secret on the Supabase project:
//   GITHUB_PAT       (fine-grained PAT, Actions: Read and write)
// Optional overrides:
//   GITHUB_OWNER     default beebeambap
//   GITHUB_REPO      default busy-day
//   GITHUB_WORKFLOW  default daily-compose.yml

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const INTENT_IDS = new Set([
  "calm", "warm", "wistful", "lively", "after_rain", "sleep",
]);

function j(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function kstHHMM(): string {
  const now = new Date(Date.now() + 9 * 3600 * 1000); // UTC -> KST
  const hh = String(now.getUTCHours()).padStart(2, "0");
  const mm = String(now.getUTCMinutes()).padStart(2, "0");
  return `${hh}${mm}`;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return j({ error: "method not allowed" }, 405);
  }

  let body: any = {};
  try { body = await req.json(); }
  catch { return j({ error: "bad json" }, 400); }

  const date     = String(body.date      ?? "today").slice(0, 16);
  const city     = String(body.city      ?? "seoul").slice(0, 32);
  const intentId = String(body.intent_id ?? "").slice(0, 32);
  if (!INTENT_IDS.has(intentId)) {
    return j({ error: "invalid intent_id" }, 400);
  }

  const pat   = Deno.env.get("GITHUB_PAT");
  const owner = Deno.env.get("GITHUB_OWNER")    ?? "beebeambap";
  const repo  = Deno.env.get("GITHUB_REPO")     ?? "busy-day";
  const wf    = Deno.env.get("GITHUB_WORKFLOW") ?? "daily-compose.yml";
  if (!pat) return j({ error: "server missing GITHUB_PAT" }, 500);

  const variantId = `user-${kstHHMM()}-${intentId}`;

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
        inputs: { date, city, variant: variantId, intent: intentId },
      }),
    },
  );

  if (!ghResp.ok) {
    const text = await ghResp.text();
    return j({
      error: "dispatch failed", status: ghResp.status, detail: text,
    }, 502);
  }

  return j({
    variant_id: variantId,
    intent_id:  intentId,
    date, city,
    eta_sec: 90,
  });
});
