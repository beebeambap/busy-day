import { bindGate } from "./auth.js";
import { CalendarView } from "./calendar.js";
import { DetailPanel } from "./player.js";
import {
  findVariant,
  fetchVariants,
  triggerCompose,
  triggerTape,
  triggerRerender,
} from "./api.js";
import { DEFAULT_CITY, DEFAULT_CITY_NAME } from "./config.js";
import { TAPE_LABELS } from "./tapes.js";

const $ = (id) => document.getElementById(id);

// Mood + situational lives in a single grid because the user picks
// exactly one. The two clusters are distinguished only visually
// (line break between them via blank "spacer" — kept simple here).
const INTENTS = [
  // emotional
  { id: "calm",       label: "차분하게",     sub: "조용한 무드" },
  { id: "warm",       label: "따뜻하게",     sub: "포근한 톤" },
  { id: "wistful",    label: "쓸쓸하게",     sub: "단조 기울임" },
  { id: "lively",     label: "활기차게",     sub: "빠른 BPM" },
  { id: "after_rain", label: "비 온 뒤처럼", sub: "촉촉한 잔향" },
  { id: "sleep",      label: "잠들기 전",    sub: "느린 BPM" },
  // situational (manual flow only — auto cron always fires at 06:00 KST)
  { id: "dawn",       label: "새벽",         sub: "거의 정적" },
  { id: "commute",    label: "출근길",       sub: "살짝 빠른" },
  { id: "nap",        label: "낮잠",         sub: "오후 2시" },
  { id: "focus",      label: "작업 중",      sub: "반복적" },
  { id: "walk",       label: "산책",         sub: "워킹 템포" },
];

const GENRES = [
  { id: "",              label: "자동",       sub: "날씨가 결정" },
  { id: "ambient",       label: "Ambient",    sub: "잔잔한 패드" },
  { id: "neo_classical", label: "Neoclassical", sub: "클래시컬" },
  { id: "folk",          label: "Folk",       sub: "어쿠스틱" },
  { id: "lo_fi",         label: "Lo-fi",      sub: "흐리게" },
  { id: "jazz_ballad",   label: "Jazz Ballad", sub: "재즈" },
  { id: "bossa_nova",    label: "Bossa Nova", sub: "보사" },
];

const INSTRUMENTS = [
  { id: "",          label: "자동",       icon: "·",  sub: "장르 기본" },
  { id: "piano",     label: "피아노",     icon: "🎹", sub: "그랜드" },
  { id: "rhodes",    label: "일렉피아노", icon: "🎹", sub: "Rhodes" },
  { id: "nylon",     label: "나일론 기타", icon: "🎸", sub: "어쿠스틱" },
  { id: "violin",    label: "바이올린",   icon: "🎻", sub: "고음현" },
  { id: "viola",     label: "비올라",     icon: "🎻", sub: "중음현" },
  { id: "cello",     label: "첼로",       icon: "🎻", sub: "저음현" },
  { id: "flute",       label: "플루트",     icon: "🎵", sub: "목관" },
  { id: "tin_whistle", label: "틴 휘슬",    icon: "🎶", sub: "아일랜드 휘슬" },
  { id: "harp",        label: "하프",       icon: "🎶", sub: "현악·플럭" },
  { id: "marimba",     label: "마림바",     icon: "🥁", sub: "말렛" },
  { id: "music_box",   label: "음악 상자",  icon: "🔔", sub: "셀레스타" },
  { id: "horn",        label: "호른",       icon: "📯", sub: "프렌치 혼" },
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
    if (onTick) onTick((Date.now() - start) / 1000);
    const row = await findVariant(city, dateIso, variantId);
    if (row) return row;
    await new Promise((r) => setTimeout(r, 6000));
  }
  throw new Error("timeout");
}

function makeIntentModal({ onSubmit }) {
  const root        = $("intent");
  const intentEl    = $("intent-grid");
  const genreEl     = $("genre-grid");
  const instEl      = $("instrument-grid");
  const submitBtn   = $("intent-submit");
  const closeBtn    = $("intent-close");

  let pickedIntent = null;
  let pickedGenre  = "";   // "" = 자동
  let pickedInstr  = "";   // "" = 자동

  function paintActive(container, value) {
    for (const b of container.querySelectorAll("button")) {
      b.classList.toggle("active", b.dataset.value === value);
    }
  }

  function buildBtn(item, kind) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.value = item.id;
    if (kind === "instrument") {
      b.innerHTML =
        `<span class="icon">${item.icon}</span>${item.label}` +
        `<span class="sub">${item.sub}</span>`;
    } else {
      b.innerHTML = `${item.label}<span class="sub">${item.sub}</span>`;
    }
    b.addEventListener("click", () => {
      if (kind === "intent") {
        pickedIntent = item.id;
        paintActive(intentEl, item.id);
        submitBtn.disabled = false;
      } else if (kind === "genre") {
        pickedGenre = item.id;
        paintActive(genreEl, item.id);
      } else {
        pickedInstr = item.id;
        paintActive(instEl, item.id);
      }
    });
    return b;
  }

  function render() {
    intentEl.innerHTML = "";
    for (const i of INTENTS) intentEl.appendChild(buildBtn(i, "intent"));
    genreEl.innerHTML = "";
    for (const g of GENRES) genreEl.appendChild(buildBtn(g, "genre"));
    instEl.innerHTML = "";
    for (const i of INSTRUMENTS) instEl.appendChild(buildBtn(i, "instrument"));
    paintActive(intentEl, pickedIntent);
    paintActive(genreEl,  pickedGenre);
    paintActive(instEl,   pickedInstr);
    submitBtn.disabled = !pickedIntent;
  }

  function open() {
    pickedIntent = null;
    pickedGenre  = "";
    pickedInstr  = "";
    render();
    submitBtn.hidden = false;
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
  }
  function close() {
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
  }

  submitBtn.addEventListener("click", () => {
    if (!pickedIntent) return;
    onSubmit({
      intent_id:     pickedIntent,
      genre_id:      pickedGenre || null,
      instrument_id: pickedInstr || null,
    });
  });

  closeBtn.addEventListener("click", close);
  root.addEventListener("click", (e) => { if (e.target === root) close(); });
  document.addEventListener("keydown", (e) => {
    if (!root.hidden && e.key === "Escape") close();
  });

  return { open, close };
}

function makeProgressPopup() {
  const root = $("progress-modal");
  const bar  = $("prog-bar");
  const eta  = $("prog-eta");
  const stat = $("prog-status");

  function show(etaSec) {
    bar.value = 0;
    eta.textContent = `예상 ${fmtSec(etaSec)}`;
    stat.textContent = "워크플로 호출 중…";
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
  }
  function tick(elapsedSec, etaSec) {
    bar.value = Math.min(95, (elapsedSec / etaSec) * 100);
    eta.textContent = `${fmtSec(elapsedSec)} / ${fmtSec(etaSec)}`;
    stat.textContent = "곡을 빚는 중…";
  }
  function fail(msg) {
    stat.textContent = `실패: ${msg}`;
    setTimeout(hide, 2500);
  }
  function hide() {
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
  }
  return { show, tick, fail, hide };
}

function boot() {
  $("city-name").textContent = DEFAULT_CITY_NAME;

  const progress = makeProgressPopup();

  // Tape trigger: lives here (not in DetailPanel) so it can share the
  // progress popup with the intent flow and refresh the calendar.
  // DetailPanel just calls back when the user clicks "편곡하기".
  async function runTapeTrigger({ sourceId, sourceDate, tapeId }) {
    const eta = 45;
    const dateIso = sourceDate || todayKST();
    progress.show(eta);
    try {
      const r = await triggerTape({
        source_song_id: sourceId,
        tape_id:        tapeId,
      });
      const realEta = r.eta_sec || eta;
      progress.tick(0, realEta);
      const row = await pollForVariant(
        DEFAULT_CITY, dateIso, r.variant_id, realEta,
        (elapsed) => progress.tick(elapsed, realEta),
      );
      progress.hide();
      await cal.render();
      const variants = await fetchVariants(DEFAULT_CITY, dateIso);
      detail.open(row, variants);
    } catch (err) {
      console.error(err);
      const presetLabel = TAPE_LABELS[tapeId]?.label || tapeId;
      progress.fail(`${presetLabel} 편곡 실패: ${err.message || err}`);
    }
  }

  // Re-render trigger: re-bakes a published song's audio from its stored
  // IR with the latest render settings (acoustic salt, channel balance).
  // No new row is created — the same Storage files are overwritten — so
  // we just dispatch, wait the ETA, and return true so the DetailPanel
  // can reload the (same-URL) MIDI with a cache-bust.
  async function runRerender({ city, date, variant, to }) {
    const eta = to ? 90 : 40;
    progress.show(eta);
    try {
      const r = await triggerRerender({ city, date, variant, to });
      const realEta = r.eta_sec || eta;
      const start = Date.now();
      await new Promise((resolve) => {
        const iv = setInterval(() => {
          const elapsed = (Date.now() - start) / 1000;
          progress.tick(elapsed, realEta);
          if (elapsed >= realEta) { clearInterval(iv); resolve(); }
        }, 1000);
      });
      progress.hide();
      return true;
    } catch (err) {
      console.error(err);
      progress.fail(`재렌더 실패: ${err.message || err}`);
      return false;
    }
  }

  const detail = new DetailPanel({
    root:          $("detail"),
    onTapeTrigger: runTapeTrigger,
    onPinChange:   () => cal.render(),
    onRerender:    runRerender,
  });

  const cal = new CalendarView({
    gridEl:  $("grid"),
    labelEl: $("month-label"),
    prevBtn: $("prev-month"),
    nextBtn: $("next-month"),
    onDayClick: (song, variants) => detail.open(song, variants),
  });

  // wire weather filter
  const filterEl = $("weather-filter");
  filterEl.addEventListener("change", () => {
    cal.setFilter(filterEl.value || null);
  });

  const intentModal = makeIntentModal({
    onSubmit: async ({ intent_id, genre_id, instrument_id }) => {
      const eta = 90;
      intentModal.close();
      progress.show(eta);
      const dateIso = todayKST();
      try {
        const r = await triggerCompose({
          city:          DEFAULT_CITY,
          date:          dateIso,
          intent_id,
          genre_id,
          instrument_id,
        });
        const realEta = r.eta_sec || eta;
        progress.tick(0, realEta);
        const row = await pollForVariant(
          DEFAULT_CITY, dateIso, r.variant_id, realEta,
          (elapsed) => progress.tick(elapsed, realEta),
        );
        progress.hide();
        await cal.render();
        const variants = await fetchVariants(DEFAULT_CITY, dateIso);
        detail.open(row, variants);
      } catch (err) {
        console.error(err);
        progress.fail(err.message || String(err));
      }
    },
  });

  $("make-btn").addEventListener("click", () => intentModal.open());

  // ── range re-render modal ──────────────────────────────────────
  const rrModal  = $("rerender-modal");
  const rrFrom   = $("rerender-from");
  const rrTo     = $("rerender-to");
  const rrStatus = $("rerender-range-status");
  const rrRun    = $("rerender-range-run");

  function openRrModal() {
    const today = todayKST();
    if (!rrFrom.value) rrFrom.value = today;
    if (!rrTo.value)   rrTo.value   = today;
    rrStatus.textContent = "—";
    rrModal.hidden = false;
    rrModal.setAttribute("aria-hidden", "false");
  }
  function closeRrModal() {
    rrModal.hidden = true;
    rrModal.setAttribute("aria-hidden", "true");
  }

  $("rerender-range-btn").addEventListener("click", openRrModal);
  $("rerender-modal-close").addEventListener("click", closeRrModal);
  rrModal.addEventListener("click", (e) => { if (e.target === rrModal) closeRrModal(); });

  rrRun.addEventListener("click", async () => {
    const from = rrFrom.value;
    const to   = rrTo.value;
    if (!from || !to) { rrStatus.textContent = "시작·끝 날짜를 입력하세요"; return; }
    if (from > to)    { rrStatus.textContent = "시작이 끝보다 늦습니다"; return; }
    rrRun.disabled = true;
    rrStatus.textContent = "디스패치 중…";
    closeRrModal();
    // variant omitted → every variant in the range. date = range start,
    // to = range end. runRerender shares the progress popup.
    const ok = await runRerender({ city: DEFAULT_CITY, date: from, to, variant: "" });
    rrRun.disabled = false;
    if (ok) await cal.render();
  });

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
