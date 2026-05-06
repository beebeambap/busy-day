import { bindGate } from "./auth.js";
import { CalendarView } from "./calendar.js";
import { DetailPanel } from "./player.js";
import { DEFAULT_CITY_NAME } from "./config.js";

const $ = (id) => document.getElementById(id);

function boot() {
  $("city-name").textContent = DEFAULT_CITY_NAME;

  const detail = new DetailPanel({ root: $("detail") });

  const cal = new CalendarView({
    gridEl: $("grid"),
    labelEl: $("month-label"),
    prevBtn: $("prev-month"),
    nextBtn: $("next-month"),
    onDayClick: (song) => detail.open(song),
  });

  $("app").hidden = false;
  document.body.dataset.state = "ready";
  cal.render();
}

bindGate({
  gateEl: $("gate"),
  formEl: $("gate-form"),
  inputEl: $("gate-input"),
  errorEl: $("gate-error"),
  onPass: boot,
});
