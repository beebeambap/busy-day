import { publicUrl, recordPlay } from "./api.js";
import * as Tone from "https://esm.sh/tone@14.8.49";
import { Midi } from "https://esm.sh/@tonejs/midi@2.0.28";

const WEATHER_LABELS = {
  temp_c: "기온",
  temp_range: "일교차",
  humidity: "습도",
  precip_mm: "강수",
  wind_mps: "바람",
  cloud_pct: "운량",
  precip_type: "강수 형태",
};

const DOWNLOAD_KEYS = [
  ["mid_short", "MIDI 1분",   "short.mid"],
  ["mid_long",  "MIDI 2분+",  "long.mid"],
  ["svg",       "악보 SVG",   "score.svg"],
  ["musicxml",  "MusicXML",   "score.musicxml"],
  ["ir_short",  "IR (json)",  "ir-short.json"],
];

// Salamander grand piano (Tone.js reference dataset, ~6 MB total).
const SALAMANDER_BASE = "https://tonejs.github.io/audio/salamander/";
const SAMPLE_PITCHES = [
  "A0","C1","D#1","F#1","A1","C2","D#2","F#2","A2",
  "C3","D#3","F#3","A3","C4","D#4","F#4","A4","C5",
  "D#5","F#5","A5","C6",
];

// Per-genre piano release time. Longer = more pedalled / ambient feel.
const PIANO_RELEASE = {
  ambient:        3.0,
  neo_classical:  2.6,
  folk:           1.6,
  lo_fi:          2.4,
};

function makePiano(release, volume) {
  const urls = Object.fromEntries(
    SAMPLE_PITCHES.map((n) => [n, n.replace("#", "s") + ".mp3"])
  );
  return new Tone.Sampler({
    urls, baseUrl: SALAMANDER_BASE, release, volume,
  });
}

function makeRhodes(volume) {
  return new Tone.PolySynth(Tone.FMSynth, {
    harmonicity:    8,
    modulationIndex: 2,
    oscillator: { type: "sine" },
    envelope:   { attack: 0.005, decay: 0.6, sustain: 0.35, release: 1.4 },
    modulation: { type: "square" },
    modulationEnvelope: {
      attack: 0.01, decay: 0.5, sustain: 0.0, release: 0.4,
    },
    volume,
  });
}

function makeNylon(volume) {
  return new Tone.PolySynth(Tone.PluckSynth, {
    attackNoise: 0.6,
    dampening:   4200,
    resonance:   0.96,
    volume,
  });
}

function makeUprightBass(volume) {
  return new Tone.PolySynth(Tone.FMSynth, {
    harmonicity:    1.0,
    modulationIndex: 4,
    envelope:   { attack: 0.01, decay: 0.7, sustain: 0.0, release: 0.8 },
    modulation: { type: "sine" },
    modulationEnvelope: {
      attack: 0.02, decay: 0.3, sustain: 0.0, release: 0.4,
    },
    volume,
  });
}

function makeAMPad(volume) {
  return new Tone.PolySynth(Tone.AMSynth, {
    harmonicity: 1.5,
    envelope:   { attack: 0.6, decay: 0.4, sustain: 0.7, release: 1.6 },
    modulation: { type: "sine" },
    modulationEnvelope: {
      attack: 0.8, decay: 0.2, sustain: 0.7, release: 1.2,
    },
    volume,
  });
}

function makeStringPad(volume) {
  return new Tone.PolySynth(Tone.AMSynth, {
    harmonicity: 2,
    oscillator: { type: "sawtooth4" },
    envelope:   { attack: 1.2, decay: 0.5, sustain: 0.85, release: 2.6 },
    modulation: { type: "sine" },
    modulationEnvelope: {
      attack: 1.4, decay: 0.4, sustain: 0.8, release: 2.0,
    },
    volume,
  });
}

const _instruments = new Map(); // genre -> { melody, harmony, bass, ready }

function buildInstruments(genre) {
  const reverb = new Tone.Reverb({ decay: 3.6, wet: 0.34 }).toDestination();
  const ready  = [reverb.generate()];

  let melody, harmony, bass;

  if (genre === "jazz_ballad") {
    melody  = makeRhodes(-10).connect(reverb);
    harmony = makeRhodes(-18).connect(reverb);
    bass    = makeUprightBass(-12).toDestination();
  } else if (genre === "bossa_nova") {
    melody  = makeNylon(-8).connect(reverb);
    harmony = makeNylon(-14).connect(reverb);
    bass    = makeUprightBass(-10).toDestination();
  } else {
    // ambient / neo_classical / folk / lo_fi : piano-led
    const release = PIANO_RELEASE[genre] ?? 2.0;
    const isLoFi = genre === "lo_fi";
    melody = makePiano(release, isLoFi ? -8 : -4);

    if (isLoFi) {
      const lp = new Tone.Filter({
        frequency: 2400, type: "lowpass", rolloff: -12,
      });
      melody.connect(lp); lp.connect(reverb);
    } else {
      melody.connect(reverb);
    }

    if (genre === "neo_classical") {
      harmony = makeStringPad(-18).connect(reverb);
    } else {
      harmony = makeAMPad(-22).connect(reverb);
    }

    bass = makePiano(release * 0.7, -10).toDestination();
    ready.push(Tone.loaded());
  }

  const entry = { melody, harmony, bass, ready: Promise.all(ready) };
  _instruments.set(genre, entry);
  return entry;
}

async function getInstruments(genre) {
  const cached = _instruments.get(genre) || buildInstruments(genre);
  await cached.ready;
  return cached;
}

// ── filename builder ─────────────────────────────────────────────
// Examples:
//   busy-day_2026-05-06_seoul_18C-clear_D-lydian_ambient_short.mid
//   busy-day_2026-05-06_seoul_12C-rain_E-dorian_lo-fi_score.svg

function _weatherTag(w) {
  if (!w) return "";
  const tempC = w.temp_c != null ? `${Math.round(Number(w.temp_c))}C` : "";
  const cloud = Number(w.cloud_pct ?? 50);
  const sky =
    w.precip_type === "rain"      ? "rain"
    : w.precip_type === "snow"      ? "snow"
    : w.precip_type === "rain_snow" ? "sleet"
    : w.precip_type === "shower"    ? "shower"
    : cloud >= 80 ? "overcast"
    : cloud >= 40 ? "cloudy"
    : "clear";
  return [tempC, sky].filter(Boolean).join("-");
}

function _slug(s) {
  return String(s ?? "")
    .toLowerCase()
    .replace(/_/g, "-")
    .replace(/[^a-z0-9-]+/g, "")
    .replace(/^-+|-+$/g, "");
}

function buildDownloadName(song, suffix) {
  const date = song.date || "song";
  const weather = _weatherTag(song.weather);
  const genre = _slug(song.genre);
  const parts = ["busy-day", date, weather, genre]
    .filter((p) => p && p.length);
  return `${parts.join("_")}_${suffix}`;
}

function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function fmtMeta(s) {
  return [
    `${s.key_root} ${s.mode}`,
    (s.genre || "").replace(/_/g, " "),
    `${s.bpm} bpm`,
    s.meter,
  ].filter(Boolean).join(" · ");
}

function fmtWeatherValue(k, v) {
  if (v == null) return "—";
  switch (k) {
    case "temp_c":     return `${Number(v).toFixed(1)}°C`;
    case "temp_range": return `${Number(v).toFixed(1)}°C`;
    case "humidity":   return `${Math.round(Number(v))}%`;
    case "precip_mm":  return `${Number(v).toFixed(1)} mm`;
    case "wind_mps":   return `${Number(v).toFixed(1)} m/s`;
    case "cloud_pct":  return `${Math.round(Number(v))}%`;
    default:           return String(v);
  }
}

const INTENT_LABELS = {
  calm:       "차분",
  warm:       "따뜻",
  wistful:    "쓸쓸",
  lively:     "활기",
  after_rain: "비 온 뒤",
  sleep:      "잠들기 전",
};

function variantLabel(song) {
  if (song.variant_id === "auto") return "오늘";
  if (song.intent_id && INTENT_LABELS[song.intent_id]) {
    return INTENT_LABELS[song.intent_id];
  }
  return song.variant_id;
}

export class DetailPanel {
  constructor({ root }) {
    this.root        = root;
    this.dateEl      = root.querySelector("#detail-date");
    this.metaEl      = root.querySelector("#detail-meta");
    this.variantsEl  = root.querySelector("#detail-variants");
    this.scoreEl     = root.querySelector("#detail-score");
    this.scoreEmpty  = root.querySelector("#detail-score-empty");
    this.statusEl    = root.querySelector("#player-status");
    this.weatherEl   = root.querySelector("#detail-weather");
    this.downloadsEl = root.querySelector("#detail-downloads");
    this.toggleEl    = root.querySelector(".variant-toggle");
    this.playBtn     = root.querySelector("#play-btn");
    this.progressEl  = root.querySelector("#play-progress");
    this.timeEl      = root.querySelector("#play-time");

    this.midi = null;
    this.duration = 0;
    this.tickHandle = null;

    root.querySelector("#detail-close").addEventListener("click", () => this.close());
    root.addEventListener("click", (e) => { if (e.target === root) this.close(); });
    document.addEventListener("keydown", (e) => {
      if (!root.hidden && e.key === "Escape") this.close();
    });

    this.toggleEl.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-variant]");
      if (!btn) return;
      this.setVariant(btn.dataset.variant);
    });

    this.playBtn.addEventListener("click", () => this.togglePlayback());
  }

  open(song, variants = null) {
    this.song = song;
    this.variants = variants && variants.length ? variants : [song];
    this.dateEl.textContent = formatDate(song.date);
    this.metaEl.textContent = fmtMeta(song);
    this.renderVariantChips();

    const svgUrl = publicUrl(song.paths?.svg);
    this.scoreEl.innerHTML = "";
    if (svgUrl) {
      this.scoreEmpty.hidden = true;
      this.scoreEl.hidden = false;
      fetch(svgUrl)
        .then((r) => r.ok ? r.text() : Promise.reject(r.status))
        .then((svg) => { this.scoreEl.innerHTML = svg; })
        .catch(() => {
          this.scoreEl.hidden = true;
          this.scoreEmpty.hidden = false;
        });
    } else {
      this.scoreEl.hidden = true;
      this.scoreEmpty.hidden = false;
    }

    this.renderWeather(song.weather);
    this.renderDownloads(song.paths);
    this.setVariant("short");

    this.root.hidden = false;
    this.root.setAttribute("aria-hidden", "false");
  }

  close() {
    this.stop();
    this.root.hidden = true;
    this.root.setAttribute("aria-hidden", "true");
  }

  async setVariant(v) {
    this.stop();
    for (const btn of this.toggleEl.querySelectorAll("button")) {
      btn.classList.toggle("active", btn.dataset.variant === v);
    }
    this.variant = v;
    const key = v === "long" ? "mid_long" : "mid_short";
    const url = publicUrl(this.song?.paths?.[key]);
    if (!url) {
      this.statusEl.textContent = "MIDI 파일이 없습니다";
      this.playBtn.disabled = true;
      return;
    }
    this.statusEl.textContent = "MIDI 로딩 중…";
    this.playBtn.disabled = true;
    try {
      this.midi = await Midi.fromUrl(url);
      this.duration = this.midi.duration;
      this.timeEl.textContent = `0:00 / ${fmtTime(this.duration)}`;
      this.progressEl.value = 0;
      this.statusEl.textContent = "재생 준비 — 첫 재생 시 악기 로드";
      this.playBtn.disabled = false;
    } catch (err) {
      console.error(err);
      this.statusEl.textContent = "MIDI 로딩 실패";
    }
  }

  async togglePlayback() {
    if (Tone.Transport.state === "started") {
      this.stop();
      return;
    }
    await this.play();
  }

  async play() {
    if (!this.midi) return;
    this.statusEl.textContent = "악기 로드 중…";
    this.playBtn.disabled = true;
    await Tone.start();

    const genre = this.song?.genre || "ambient";
    const { melody, harmony, bass } = await getInstruments(genre);

    Tone.Transport.stop();
    Tone.Transport.cancel(0);

    const t0 = 0.05;
    this.midi.tracks.forEach((track) => {
      const name = (track.name || "").toLowerCase();
      let inst;
      if (name.includes("harmony"))   inst = harmony;
      else if (name.includes("bass")) inst = bass;
      else                            inst = melody;

      track.notes.forEach((note) => {
        Tone.Transport.schedule((time) => {
          inst.triggerAttackRelease(
            note.name, note.duration, time, note.velocity * 0.85,
          );
        }, t0 + note.time);
      });
    });

    Tone.Transport.scheduleOnce(() => this.stop(), t0 + this.duration + 1.5);

    Tone.Transport.start();
    this.playBtn.textContent = "■";
    this.playBtn.disabled = false;
    this.statusEl.textContent = `재생 중 — ${genre.replace(/_/g, " ")}`;
    this._tick();

    if (this.song) recordPlay(this.song.id, this.variant).catch(() => {});
  }

  stop() {
    Tone.Transport.stop();
    Tone.Transport.cancel(0);
    if (this.tickHandle) {
      cancelAnimationFrame(this.tickHandle);
      this.tickHandle = null;
    }
    this.playBtn.textContent = "▶";
    this.progressEl.value = 0;
    this.timeEl.textContent = `0:00 / ${fmtTime(this.duration)}`;
    if (this.statusEl) this.statusEl.textContent = "재생 준비 완료";
  }

  _tick() {
    const update = () => {
      const t = Tone.Transport.seconds;
      const pct = Math.min(100, (t / Math.max(this.duration, 0.001)) * 100);
      this.progressEl.value = pct;
      this.timeEl.textContent = `${fmtTime(t)} / ${fmtTime(this.duration)}`;
      if (Tone.Transport.state === "started") {
        this.tickHandle = requestAnimationFrame(update);
      }
    };
    this.tickHandle = requestAnimationFrame(update);
  }

  renderVariantChips() {
    this.variantsEl.innerHTML = "";
    if (!this.variants || this.variants.length <= 1) {
      this.variantsEl.hidden = true;
      return;
    }
    this.variantsEl.hidden = false;
    for (const v of this.variants) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = variantLabel(v);
      if (v.id === this.song.id) b.classList.add("active");
      b.addEventListener("click", () => {
        if (v.id === this.song.id) return;
        this.swapTo(v);
      });
      this.variantsEl.appendChild(b);
    }
  }

  swapTo(song) {
    this.stop();
    this.song = song;
    this.metaEl.textContent = fmtMeta(song);

    const svgUrl = publicUrl(song.paths?.svg);
    this.scoreEl.innerHTML = "";
    if (svgUrl) {
      this.scoreEmpty.hidden = true;
      this.scoreEl.hidden = false;
      fetch(svgUrl)
        .then((r) => r.ok ? r.text() : Promise.reject(r.status))
        .then((svg) => { this.scoreEl.innerHTML = svg; })
        .catch(() => {
          this.scoreEl.hidden = true;
          this.scoreEmpty.hidden = false;
        });
    }
    this.renderDownloads(song.paths);
    this.renderVariantChips();
    this.setVariant("short");
  }

  renderWeather(w) {
    this.weatherEl.innerHTML = "";
    if (!w || typeof w !== "object") return;
    for (const [k, label] of Object.entries(WEATHER_LABELS)) {
      if (!(k in w)) continue;
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = fmtWeatherValue(k, w[k]);
      this.weatherEl.append(dt, dd);
    }
  }

  renderDownloads(paths) {
    this.downloadsEl.innerHTML = "";
    if (!paths || !this.song) return;
    for (const [key, label, suffix] of DOWNLOAD_KEYS) {
      const url = publicUrl(paths[key]);
      if (!url) continue;
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = url;
      a.download = buildDownloadName(this.song, suffix);
      a.textContent = label;
      li.appendChild(a);
      this.downloadsEl.appendChild(li);
    }
  }
}

function formatDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const month = date.toLocaleString("en-US", { month: "long" });
  return `${month} ${d}, ${y}`;
}
