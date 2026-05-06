import { bindGate } from "./auth.js";
import { CalendarView } from "./calendar.js";
import { DetailPanel } from "./player.js";
import { findVariant, fetchVariants, triggerCompose } from "./api.js";
import { DEFAULT_CITY, DEFAULT_CITY_NAME } from "./config.js";

const $ = (id) => document.getElementById(id);

const INTENTS = [
  { id: "calm",       label: "차분하게",   sub: "조용한 무드" },
  { id: "warm",       label: "따뜻하게",   sub: "포근한 톤" },
  { id: "wistful",    label: "쓸쓸하게",   sub: "단조 기울임" },
  { id: "lively",     label: "활기차게",   sub: "보사·포크 쪽" },
  { id: "after_rain", label: "비 온 뒤처럼", sub: "촉촉한 잔향" },
  { id: "sleep",      label: "잠들기 전",   sub: "느린 BPM" },
];

function todayKST() {
  // KST = UTC+9. We want a YYYY-MM-DD that matches the server's KST clock.
  const t = new Date(Date.now() + 9 * 3600 * 1000);
  return t.toISOString().slice(0, 10);
}

async function pollForVariant(city, dateIso, variantId, etaSec) {
  const deadline = Date.now() + (etaSec + 90) * 1000;
  while (Date.now() < deadline) {
    const row = await findVariant(city, dateIso, variantId);
    if (row) return row;
    await new Promise((r) => setTimeout(r, 6000));
  }
  throw new Error("timeout");
}

function makeIntentModal({ onPick }) {
  const root = $("intent");
  const grid = $("intent-grid");
  const status = $("intent-status");
  const closeBtn = $("intent-close");

  function render() {
    grid.innerHTML = "";
    for (const i of INTENTS) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.intentId = i.id;
      b.innerHTML = `${i.label}<span class="sub">${i.sub}</span>`;
      b.addEventListener("click", () => onPick(i.id, b));
      grid.appendChild(b);
    }
  }

  function open() {
    render();
    status.hidden = true;
    status.textContent = "";
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
  }
  function close() {
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
  }
  function setStatus(msg) {
    status.hidden = !msg;
    status.textContent = msg || "";
  }
  function disableAll(disabled) {
    for (const b of grid.querySelectorAll("button")) b.disabled = disabled;
  }

  closeBtn.addEventListener("click", close);
  root.addEventListener("click", (e) => {
    if (e.target === root) close();
  });
  document.addEventListener("keydown", (e) => {
    if (!root.hidden && e.key === "Escape") close();
  });

  return { open, close, setStatus, disableAll };
}

function boot() {
  $("city-name").textContent = DEFAULT_CITY_NAME;

  const detail = new DetailPanel({ root: $("detail") });

  const cal = new CalendarView({
    gridEl:  $("grid"),
    labelEl: $("month-label"),
    prevBtn: $("prev-month"),
    nextBtn: $("next-month"),
    onDayClick: (song, variants) => detail.open(song, variants),
  });

  const intentModal = makeIntentModal({
    onPick: async (intentId, btn) => {
      intentModal.disableAll(true);
      intentModal.setStatus("워크플로 호출 중…");
      const dateIso = todayKST();
      try {
        const r = await triggerCompose({
          city:      DEFAULT_CITY,
          date:      dateIso,
          intent_id: intentId,
        });
        intentModal.setStatus(
          `곡을 빚는 중… (약 ${r.eta_sec || 90}초)`
        );
        const row = await pollForVariant(
          DEFAULT_CITY, dateIso, r.variant_id, r.eta_sec || 90,
        );
        intentModal.close();
        await cal.render();
        const variants = await fetchVariants(DEFAULT_CITY, dateIso);
        detail.open(row, variants);
      } catch (err) {
        console.error(err);
        intentModal.setStatus(`실패: ${err.message || err}`);
        intentModal.disableAll(false);
      }
    },
  });

  $("make-btn").addEventListener("click", () => intentModal.open());

  $("app").hidden = false;
  document.body.dataset.state = "ready";
  cal.render();
}

bindGate({
  gateEl:  $("gate"),
  formEl:  $("gate-form"),
  inputEl: $("gate-input"),
  errorEl: $("gate-error"),
  onPass:  boot,
});
