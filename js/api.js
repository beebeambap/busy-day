import {
  SUPABASE_URL,
  SUPABASE_PUBLISHABLE_KEY,
  STORAGE_BUCKET,
} from "./config.js";

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.46.1";

export const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const STORAGE_PREFIX = `${SUPABASE_URL}/storage/v1/object/public/${STORAGE_BUCKET}/`;

export function publicUrl(path) {
  if (!path) return null;
  return STORAGE_PREFIX + path.replace(/^\/+/, "");
}

const SONG_COLS =
  "id, city_id, date, variant_id, intent_id, instrument_id, " +
  "key_root, mode, genre, bpm, meter, duration_short_sec, " +
  "duration_long_sec, weather, paths, created_at";

// Order so 'auto' shows first, then user variants by created_at desc.
function _sortVariants(rows) {
  return rows.slice().sort((a, b) => {
    if (a.variant_id === "auto" && b.variant_id !== "auto") return -1;
    if (b.variant_id === "auto" && a.variant_id !== "auto") return 1;
    return (b.created_at || "").localeCompare(a.created_at || "");
  });
}

export async function fetchMonth(cityId, year, month) {
  const start = `${year}-${String(month).padStart(2, "0")}-01`;
  const nextY = month === 12 ? year + 1 : year;
  const nextM = month === 12 ? 1 : month + 1;
  const end = `${nextY}-${String(nextM).padStart(2, "0")}-01`;

  const { data, error } = await supabase
    .from("songs")
    .select(SONG_COLS)
    .eq("city_id", cityId)
    .gte("date", start)
    .lt("date", end)
    .order("date", { ascending: true });

  if (error) throw error;

  const byDate = new Map(); // date -> array of variants (auto first)
  for (const row of data ?? []) {
    const list = byDate.get(row.date) || [];
    list.push(row);
    byDate.set(row.date, list);
  }
  for (const [d, list] of byDate) byDate.set(d, _sortVariants(list));
  return byDate;
}

export async function fetchVariants(cityId, dateIso) {
  const { data, error } = await supabase
    .from("songs")
    .select(SONG_COLS)
    .eq("city_id", cityId)
    .eq("date", dateIso)
    .order("created_at", { ascending: true });
  if (error) throw error;
  return _sortVariants(data || []);
}

export async function findVariant(cityId, dateIso, variantId) {
  const { data, error } = await supabase
    .from("songs")
    .select(SONG_COLS)
    .eq("city_id", cityId)
    .eq("date", dateIso)
    .eq("variant_id", variantId)
    .limit(1);
  if (error) throw error;
  return (data && data[0]) || null;
}

export async function triggerCompose(
  { city, date, intent_id, genre_id, instrument_id },
) {
  const url = `${SUPABASE_URL}/functions/v1/trigger`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "apikey":         SUPABASE_PUBLISHABLE_KEY,
      "Authorization": `Bearer ${SUPABASE_PUBLISHABLE_KEY}`,
    },
    body: JSON.stringify({ city, date, intent_id, genre_id, instrument_id }),
  });
  const text = await r.text();
  let body;
  try { body = JSON.parse(text); } catch { body = { error: text }; }
  if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
  return body;          // { variant_id, intent_id, instrument_id, eta_sec, ... }
}

export async function recordPlay(songId, variant) {
  await supabase.from("plays").insert({
    song_id: songId,
    variant,
    completed: false,
  });
}
