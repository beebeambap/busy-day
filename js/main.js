import { bindGate } from "./auth.js";
import { CalendarView } from "./calendar.js";
import { DetailPanel } from "./player.js";
import { findVariant, fetchVariants, triggerCompose } from "./api.js";
import { DEFAULT_CITY, DEFAULT_CITY_NAME } from "./config.js";

const $ = (id) => document.getElementById(id);

const INTENTS = [
  { id: "calm",       label: "차분하게",     sub: "조용한 무드" },
  { id: "warm",       label: "따뜻하게",     sub: "포근한 톤" },
  { id: "wistful",    label: "쓸쓸하게",     sub: "단조 기울임" },
  { id: "lively",     label: "활기차게",     sub: "빠른 BPM" },
  { id: "after_rain", label: "비 온 뒤처럼", sub: "촉촉한 잔향" },
  { id: "sleep",      label: "잠들기 전",    sub: "느린 BPM" },
];

// 시간/상황 무드 — 자동 cron 은 항상 06:00 KST 에 도는 단일 시각이라
// 이 카테고리는 수동 트리거에서만 의미가 있다.
const SITUATIONS = [
  { id: "dawn",    label: "새벽",     sub: "거의 정적" },
  { id: "commute", label: "출근길",   sub: "살짝 빠른" },
  { id: "nap",     label: "낮잠",     sub: "오후 2시 톤" },
  { id: "focus",   label: "작업 중",  sub: "반복적·집중" },
  { id: "walk",    label: "산책",     sub: "워킹 템포" },
];

const INSTRUMENTS = [
  { id: "",          label: "자동",       icon: "·",  sub: "장르 기본" },
  { id: "piano",     label: "피아노",     icon: "🎹", sub: "그랜드" },
  { id: "rhodes",    label: "일렉피아노", icon: "🎹", sub: "Rhodes" },
  { id: "nylon",     label: "나일론 기타", icon: "🎸", sub: "어쿠스틱" },
  { id: "strings",   label: "현악기",     icon: "🎻", sub: "스트링즈" },
  { id: "music_box", label: "음악 상자",  icon: "🔔", sub: "셀레스타" },
  { id: "horn",      label: "호른",       icon: "📯", sub: "프렌치 혼" },
];

function todayKST() {
  const t = new Date(Date.now() + 9 * 3600 * 1000);
  return t.toISOString().slice(0, 10);
}

function fmtSec(s) {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m ? `${m}:${String(r).padStart(2, "0")}` : `${s}초`;
}

async function pollForVariant(
  city, dateIso, variantId, etaSec, onTick,
) {
  const start = Date.now();
  const deadline = start + (etaSec + 90) * 1000;
  while (Date.now() < deadline) {
    if (onTick) {
      const elapsed = (Date.now() - start) / 1000;
      onTick(elapsed);
    }
    const row = await findVariant(city, dateIso, variantId);
    if (row) return row;
    await new Promise((r) => setTimeout(r, 6000));
  }
  throw new Error("timeout");
}

function makeIntentModal({ onSubmit }) {
  const root        = $("intent");
  const intentEl    = $("intent-grid");
  const sitEl       = $("situation-grid");
  const instEl      = $("instrument-grid");
  const submitBtn   = $("intent-submit");
  const closeBtn    = $("intent-close");
  const progressBox = $("intent-progress");
  const statusEl    = $("intent-status");
  const barEl       = $("intent-bar");
  const etaEl       = $("intent-eta");

  // pickedIntent holds the chosen id (across both intent + situation
  // grids — they're mutually exclusive).
  let pickedIntent = null;
  let pickedInstrument = "";   // "" = auto

  function paintActiveAcrossGrids(value) {
    for (const grid of [intentEl, sitEl]) {
      for (const b of grid.querySelectorAll("button")) {
        b.classList.toggle("active", b.dataset.value === value);
      }
    }
  }

  function paintActive(container, value) {
    for (const b of container.querySelectorAll("button")) {
      b.classList.toggle("active", b.dataset.value === value);
    }
  }

  function buildIntentBtn(item) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.value = item.id;
    b.innerHTML = `${item.label}<span class="sub">${item.sub}</span>`;
    b.addEventListener("click", () => {
      pickedIntent = item.id;
      paintActiveAcrossGrids(item.id);
      submitBtn.disabled = false;
    });
    return b;
  }

  function render() {
    intentEl.innerHTML = "";
    sitEl.innerHTML = "";
    for (const i of INTENTS)     intentEl.appendChild(buildIntentBtn(i));
    for (const s of SITUATIONS)  sitEl.appendChild(buildIntentBtn(s));

    instEl.innerHTML = "";
    for (const i of INSTRUMENTS) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.value = i.id;
      b.innerHTML =
        `<span class="icon">${i.icon}</span>${i.label}` +
        `<span class="sub">${i.sub}</span>`;
      if (i.id === pickedInstrument) b.classList.add("active");
      b.addEventListener("click", () => {
        pickedInstrument = i.id;
        paintActive(instEl, i.id);
      });
      instEl.appendChild(b);
    }
    paintActiveAcrossGrids(pickedIntent);
    submitBtn.disabled = !pickedIntent;
  }

  function open() {
    pickedIntent = null;
    pickedInstrument = "";
    render();
    progressBox.hidden = true;
    barEl.value = 0;
    statusEl.textContent = "곡을 빚는 중…";
    etaEl.textContent = "—";
    submitBtn.hidden = false;
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
  }
  function close() {
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
  }

  function showProgress(etaSec) {
    progressBox.hidden = false;
    submitBtn.hidden = true;
    barEl.value = 0;
    statusEl.textContent = "워크플로 호출 중…";
    etaEl.textContent = `예상 ${fmtSec(etaSec)}`;
  }
  function tickProgress(elapsedSec, etaSec) {
    // soft-cap at 95% so it doesn't sit at 100% while we keep polling
    const pct = Math.min(95, (elapsedSec / etaSec) * 100);
    barEl.value = pct;
    statusEl.textContent = "곡을 빚는 중…";
    etaEl.textContent = `${fmtSec(elapsedSec)} / ${fmtSec(etaSec)}`;
  }
  function failProgress(msg) {
    barEl.value = 0;
    statusEl.textContent = `실패: ${msg}`;
    etaEl.textContent = "";
    submitBtn.hidden = false;
    submitBtn.disabled = !pickedIntent;
  }

  function disableInputs(disabled) {
    for (const b of root.querySelectorAll(
      "button:not(#intent-close):not(#intent-submit)",
    )) {
      b.disabled = disabled;
    }
  }

  submitBtn.addEventListener("click", () => {
    if (!pickedIntent) return;
    onSubmit({
      intent_id: pickedIntent,
      instrument_id: pickedInstrument || null,
    });
  });

  closeBtn.addEventListener("click", close);
  root.addEventListener("click", (e) => {
    if (e.target === root) close();
  });
  document.addEventListener("keydown", (e) => {
    if (!root.hidden && e.key === "Escape") close();
  });

  return { open, close, showProgress, tickProgress, failProgress,
           disableInputs };
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
    onSubmit: async ({ intent_id, instrument_id }) => {
      const eta = 90;
      intentModal.disableInputs(true);
      intentModal.showProgress(eta);
      const dateIso = todayKST();
      try {
        const r = await triggerCompose({
          city:          DEFAULT_CITY,
          date:          dateIso,
          intent_id,
          instrument_id,
        });
        const realEta = r.eta_sec || eta;
        intentModal.tickProgress(0, realEta);
        const row = await pollForVariant(
          DEFAULT_CITY, dateIso, r.variant_id, realEta,
          (elapsed) => intentModal.tickProgress(elapsed, realEta),
        );
        intentModal.close();
        await cal.render();
        const variants = await fetchVariants(DEFAULT_CITY, dateIso);
        detail.open(row, variants);
      } catch (err) {
        console.error(err);
        intentModal.failProgress(err.message || String(err));
        intentModal.disableInputs(false);
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
