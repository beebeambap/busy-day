import { fetchMonth } from "./api.js";
import { DEFAULT_CITY } from "./config.js";

// Pure function of song.weather. Returns a Set of category tags.
// Mirrors main.js.categorizeWeather but lives here to avoid a circular
// import (main.js imports CalendarView from this file).
function categorizeWeather(w) {
  if (!w) return new Set();
  const tags = new Set();
  const pcp   = Number(w.precip_mm  ?? 0);
  const wind  = Number(w.wind_mps   ?? 0);
  const cloud = Number(w.cloud_pct  ?? 50);
  const tempC = Number(w.temp_c     ?? 15);
  const humid = Number(w.humidity   ?? 60);
  const ptype = String(w.precip_type ?? "none");

  if (ptype === "snow" || ptype === "rain_snow") tags.add("snow");
  else if (pcp > 0.1 || ptype === "rain" || ptype === "shower") tags.add("rain");
  else if (cloud >= 70) tags.add("cloudy");
  else if (cloud < 30) tags.add("clear");
  else tags.add("cloudy");

  if (wind >= 5)        tags.add("windy");
  if (tempC <= 0)       tags.add("cold");
  if (tempC >= 26)      tags.add("hot");
  if (humid >= 80 && pcp < 0.5) tags.add("humid");
  return tags;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function ymd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function startOfMonth(year, month) {
  return new Date(year, month - 1, 1);
}

function gridStart(year, month) {
  const first = startOfMonth(year, month);
  const offset = first.getDay();          // Sun = 0
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  return start;
}

export class CalendarView {
  constructor({ gridEl, labelEl, prevBtn, nextBtn, onDayClick }) {
    this.gridEl = gridEl;
    this.labelEl = labelEl;
    this.onDayClick = onDayClick;
    // null = all (worst hidden); "pin_legendary" / "pin_worst"; weather tag
    this.filter = null;
    const today = new Date();
    this.year = today.getFullYear();
    this.month = today.getMonth() + 1;

    prevBtn.addEventListener("click", () => this.shift(-1));
    nextBtn.addEventListener("click", () => this.shift(+1));
  }

  setFilter(tag) {
    this.filter = tag || null;
    this.render();
  }

  // Apply the active filter to a list of variants for one date cell.
  // Returns the subset to show (may be empty).
  _applyFilter(variants) {
    if (!variants || !variants.length) return [];
    if (this.filter === "pin_legendary") {
      return variants.filter((v) => v.pin_type === "legendary");
    }
    if (this.filter === "pin_worst") {
      return variants.filter((v) => v.pin_type === "worst");
    }
    // Default: hide worst songs, then optionally apply weather filter.
    let result = variants.filter((v) => v.pin_type !== "worst");
    if (this.filter) {
      result = result.filter((v) =>
        categorizeWeather(v.weather).has(this.filter),
      );
    }
    return result;
  }

  async shift(delta) {
    let m = this.month + delta;
    let y = this.year;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1;  y += 1; }
    this.year = y;
    this.month = m;
    await this.render();
  }

  async render() {
    this.labelEl.textContent = `${MONTH_NAMES[this.month - 1]} ${this.year}`;
    this.gridEl.innerHTML = "";

    let songs;
    try {
      songs = await fetchMonth(DEFAULT_CITY, this.year, this.month);
    } catch (err) {
      console.error("[calendar] fetch failed:", err);
      songs = new Map();
    }

    const todayStr = ymd(new Date());
    const start = gridStart(this.year, this.month);
    const cells = 42;                     // 6 weeks

    for (let i = 0; i < cells; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      const dStr = ymd(d);

      const cell = document.createElement("div");
      cell.className = "cell";
      const inMonth = d.getMonth() + 1 === this.month;
      if (!inMonth) cell.classList.add("outside");
      if (dStr > todayStr) cell.classList.add("future");
      if (dStr === todayStr) cell.classList.add("today");

      const num = document.createElement("span");
      num.className = "num";
      num.textContent = d.getDate();
      cell.appendChild(num);

      const allVariants = songs.get(dStr) || [];
      const variants = this._applyFilter(allVariants);

      if (variants.length && inMonth) {
        const primary = variants[0];
        cell.classList.add("has-song");
        // ⭐ badge fires when ANY variant of the day is legendary —
        // user might pin a non-primary variant (e.g., a tape) and still
        // want the day flagged. Border highlight reserved for when the
        // PRIMARY variant is legendary (stronger signal).
        const anyLegendary = variants.some((v) => v.pin_type === "legendary");
        if (primary.pin_type === "legendary") cell.classList.add("legendary");
        const tag = document.createElement("span");
        tag.className = "genre";
        tag.textContent = (primary.genre || "").replace(/_/g, " ");
        cell.appendChild(tag);
        if (anyLegendary) {
          const badge = document.createElement("span");
          badge.className = "pin-badge";
          badge.textContent = "⭐";
          cell.appendChild(badge);
        }
        if (variants.length > 1) {
          const c = document.createElement("span");
          c.className = "count";
          c.textContent = `+${variants.length - 1}`;
          cell.appendChild(c);
        }
        cell.addEventListener("click", () =>
          this.onDayClick(primary, variants),
        );
      } else if ((this.filter || allVariants.some((v) => v.pin_type === "worst")) && allVariants.length && inMonth) {
        // had songs but filter (or default worst-hiding) excluded them all
        cell.classList.add("filtered-out");
      }

      this.gridEl.appendChild(cell);
    }
  }
}
