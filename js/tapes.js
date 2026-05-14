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
  clear_hot: { label: "맑고 더운 날", icon: "🌞", short: "맑고 더운 날 편곡" },
  // planned (designed in weather-tapes-arrangement-system-v1.md):
  // rain  : "비 오는 날",  ☔
  // cold  : "한파",         🌡
  // snow  : "눈 오는 날",   ❄️
  // fog   : "흐린 날",      🌫
  // storm : "폭풍",         🌩
};

// Mirror of compose/tapes/presets.py::match_weather()
export function matchWeatherTape(weather) {
  if (!weather) return null;
  const temp   = Number(weather.temp_c    ?? 15);
  const cloud  = Number(weather.cloud_pct ?? 50);
  const precip = Number(weather.precip_mm ??  0);

  // CLEAR HOT: hot + sunny + dry. 25°C+ is summer-warm in Seoul,
  // cloud ≤ 30% reads as "clear", precip threshold filters passing
  // showers on otherwise-clear days.
  if (temp >= 25.0 && cloud <= 30.0 && precip <= 0.5) {
    return "clear_hot";
  }

  return null;
}

// Pretty label for a tape variant row (used in variant chips).
// Returns "" when the song isn't a tape variant.
export function tapeChipLabel(song) {
  if (!song?.tape_id) return "";
  const t = TAPE_LABELS[song.tape_id];
  if (!t) return song.tape_id;
  return `${t.icon} ${t.short}`;
}
