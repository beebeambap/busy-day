import { fetchMonth } from "./api.js";
import { DEFAULT_CITY } from "./config.js";

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
    const today = new Date();
    this.year = today.getFullYear();
    this.month = today.getMonth() + 1;

    prevBtn.addEventListener("click", () => this.shift(-1));
    nextBtn.addEventListener("click", () => this.shift(+1));
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

      const variants = songs.get(dStr);
      if (variants && variants.length && inMonth) {
        const primary = variants[0];   // auto first if present, else newest
        cell.classList.add("has-song");
        const tag = document.createElement("span");
        tag.className = "genre";
        tag.textContent = (primary.genre || "").replace(/_/g, " ");
        cell.appendChild(tag);
        if (variants.length > 1) {
          const c = document.createElement("span");
          c.className = "count";
          c.textContent = `+${variants.length - 1}`;
          cell.appendChild(c);
        }
        cell.addEventListener("click", () =>
          this.onDayClick(primary, variants),
        );
      }

      this.gridEl.appendChild(cell);
    }
  }
}
