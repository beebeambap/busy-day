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
  { id: "lively",     label: "활기차게",   sub: "빠른 BPM" },
  { id: "after_rain", label: "비 온 뒤처럼", sub: "촉촉한 잔향" },
  { id: "sleep",      label: "잠들기 전",   sub: "느린 BPM" },
];

const INSTRUMENTS = [
  { id: "",          label: "자동",          icon: "·",  sub: "장르 기본" },
  { id: "piano",     label: "피아노",        icon: "🎹", sub: "그랜드" },
  { id: "rhodes",    label: "일렉피아노",    icon: "🎹", sub: "Rhodes" },
  { id: "nylon",     label: "나일론 기타",   icon: "🎸", sub: "어쿠스틱" },
  { id: "strings",   label: "현악기",        icon: "🎻", sub: "스트링즈" },
  { id: "music_box", label: "음악 상자",     icon: "🔔", sub: "셀레스타" },
  { id: "horn",      label: "호른",          icon: "📯", sub: "프렌치 혼" },
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

function makeIntentModal({ onSubmit }) {
  const root      = $("intent");
  const intentEl  = $("intent-grid");
  const instEl    = $("instrument-grid");
  const submitBtn = $("intent-submit");
  const status    = $("intent-status");
  const closeBtn  = $("intent-close");

  let pickedIntent = null;
  let pickedInstrument = "";   // "" = auto

  function paintActive(container, value) {
    for (const b of container.querySelectorAll("button")) {
      b.classList.toggle("active", b.dataset.value === value);
    }
  }

  function render() {
    intentEl.innerHTML = "";
    for (const i of INTENTS) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.value = i.id;
      b.innerHTML = `${i.label}<span class="sub">${i.sub}</span>`;
      b.addEventListener("click", () => {
        pickedIntent = i.id;
        paintActive(intentEl, i.id);
        submitBtn.disabled = false;
      });
      intentEl.appendChild(b);
    }
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
    paintActive(intentEl, pickedIntent);
    submitBtn.disabled = !pickedIntent;
  }

  function open() {
    pickedIntent = null;
    pickedInstrument = "";
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
    for (const b of root.querySelectorAll("button:not(#intent-close)")) {
      b.disabled = disabled;
    }
  }

  submitBtn.addEventListener("click", () => {
    if (!pickedIntent) return;
    onSubmit({ intent_id: pickedIntent, instrument_id: pickedInstrument || null });
  });

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
    onSubmit: async ({ intent_id, instrument_id }) => {
      intentModal.disableAll(true);
      intentModal.setStatus("워크플로 호출 중…");
      const dateIso = todayKST();
      try {
        const r = await triggerCompose({
          city:          DEFAULT_CITY,
          date:          dateIso,
          intent_id,
          instrument_id,
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
