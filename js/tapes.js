// Weather Tapes — client-side preset matching + label table.
//
// MUST stay in sync with compose/tapes/presets.py:
//   - PRESETS keys (the tape_id values)
//   - match_weather() criteria
//   - label_ko strings
//
// The frontend uses these to decide which "편곡하기" button to show on
// each song's detail panel. The actual tape generation happens
// server-side via /trigger_tape -> tape-compose.yml.

export const TAPE_LABELS = {
  clear_hot:  { label: "맑고 더운 날",       icon: "🌞", short: "맑고 더운 날 편곡" },
  rain:       { label: "비 오는 날",        icon: "🌧", short: "비 오는 날 편곡" },
  shower:     { label: "소나기 오는 날",     icon: "🌦", short: "소나기 편곡" },
  snow:       { label: "눈 오는 날",        icon: "❄",  short: "눈 오는 날 편곡" },
  fog:        { label: "안개 낀 날",        icon: "🌫", short: "안개 낀 날 편곡" },
  cold_clear: { label: "춥고 맑은 날",       icon: "🥶", short: "춥고 맑은 날 편곡" },
  humid:      { label: "장마같은 끈끈한 날", icon: "💧", short: "끈끈한 날 편곡" },
  windy:      { label: "바람 부는 날",       icon: "💨", short: "바람 부는 날 편곡" },
  storm:      { label: "폭풍 치는 날",       icon: "⛈", short: "폭풍 치는 날 편곡" },
  cool_clear: { label: "선선하고 맑은 날",    icon: "🌸", short: "선선하고 맑은 날 편곡" },
};

// Mirror of compose/tapes/presets.py::match_weather() — checked in
// order of specificity (rare/dramatic conditions first).
export function matchWeatherTape(weather) {
  if (!weather) return null;
  const temp   = Number(weather.temp_c    ?? 15);
  const cloud  = Number(weather.cloud_pct ?? 50);
  const precip = Number(weather.precip_mm ??  0);
  const wind   = Number(weather.wind_mps  ??  2);
  const humid  = Number(weather.humidity  ?? 60);
  const ptype  = String(weather.precip_type ?? "none");

  // 1) SNOW — precip_type wins regardless of other conditions.
  if (ptype === "snow" || ptype === "rain_snow") return "snow";

  // 2) STORM — true storms only (heavy rain + strong wind, OR torrential).
  // Old threshold (precip≥5 AND wind≥5) caught ordinary summer showers
  // with moderate wind; bumped so only genuine storms route here.
  if ((precip >= 8.0 && wind >= 6.0) || precip >= 15.0) return "storm";

  // 3) SHOWER — KMA precip_type code 4 (소나기). Short convective rain.
  if (ptype === "shower") return "shower";

  // 4) RAIN — meaningful rain + overcast.
  if (precip >= 0.3 && cloud >= 50.0) return "rain";

  // 5) FOG — heavy cloud + humid + still air, no precip.
  if (cloud >= 80.0 && humid >= 75.0 && wind < 3.0 && precip < 0.3) return "fog";

  // 6) CLEAR_HOT — hot + clear + dry.
  if (temp >= 25.0 && cloud <= 30.0 && precip <= 0.5) return "clear_hot";

  // 7) COLD_CLEAR — freezing + clear + dry.
  if (temp <= 5.0 && cloud <= 50.0 && precip < 0.3 && humid < 65.0) return "cold_clear";

  // 8) HUMID — muggy summer, no rain.
  if (humid >= 80.0 && temp >= 22.0 && precip < 0.5) return "humid";

  // 9) WINDY — strong wind, dry.
  if (wind >= 5.0 && precip < 1.0) return "windy";

  // 10) COOL_CLEAR — mild clear-sky fallback.
  if (temp >= 12.0 && temp <= 22.0 && cloud <= 30.0 && precip < 0.3) return "cool_clear";

  return null;
}

