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

export async function fetchMonth(cityId, year, month) {
  const start = `${year}-${String(month).padStart(2, "0")}-01`;
  const nextY = month === 12 ? year + 1 : year;
  const nextM = month === 12 ? 1 : month + 1;
  const end = `${nextY}-${String(nextM).padStart(2, "0")}-01`;

  const { data, error } = await supabase
    .from("songs")
    .select(
      "id, date, key_root, mode, genre, bpm, meter, " +
        "duration_short_sec, duration_long_sec, weather, paths"
    )
    .eq("city_id", cityId)
    .gte("date", start)
    .lt("date", end)
    .order("date", { ascending: true });

  if (error) throw error;

  const byDate = new Map();
  for (const row of data ?? []) byDate.set(row.date, row);
  return byDate;
}

export async function recordPlay(songId, variant) {
  await supabase.from("plays").insert({
    song_id: songId,
    variant,
    completed: false,
  });
}
