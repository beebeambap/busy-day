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
  ["mid_short", "MIDI 1분"],
  ["mid_long",  "MIDI 2분+"],
  ["svg",       "악보 SVG"],
  ["musicxml",  "MusicXML"],
  ["ir_short",  "IR (json)"],
];

// Salamander grand piano samples — Tone.js's reference dataset, hosted by
// the project. ~6 MB across the velocity layers we ask for.
const SALAMANDER_BASE =
  "https://tonejs.github.io/audio/salamander/";
const SAMPLE_PITCHES = ["A0","C1","D#1","F#1","A1","C2","D#2","F#2","A2",
                        "C3","D#3","F#3","A3","C4","D#4","F#4","A4","C5",
                        "D#5","F#5","A5","C6"];

let pianoPromise = null;
let pad = null;     // soft pad layer for harmony track

function getPiano() {
  if (pianoPromise) return pianoPromise;
  const urls = Object.fromEntries(SAMPLE_PITCHES.map((n) => [n, n.replace("#","s") + ".mp3"]));
  const piano = new Tone.Sampler({
    urls,
    baseUrl: SALAMANDER_BASE,
    release: 1.4,
    volume: -4,
  }).toDestination();
  pianoPromise = Tone.loaded().then(() => piano);
  return pianoPromise;
}

function getPad() {
  if (pad) return pad;
  // simple AM-synth pad for the harmony layer
  pad = new Tone.PolySynth(Tone.AMSynth, {
    harmonicity: 1.5,
    envelope:   { attack: 0.6, decay: 0.4, sustain: 0.7, release: 1.4 },
    modulation: { type: "sine" },
    modulationEnvelope: { attack: 0.8, decay: 0.2, sustain: 0.7, release: 1.2 },
    volume: -22,
  });
  const verb = new Tone.Reverb({ decay: 4, wet: 0.45 }).toDestination();
  pad.connect(verb);
  return pad;
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
    case "temp_c":      return `${Number(v).toFixed(1)}°C`;
    case "temp_range":  return `${Number(v).toFixed(1)}°C`;
    case "humidity":    return `${Math.round(Number(v))}%`;
    case "precip_mm":   return `${Number(v).toFixed(1)} mm`;
    case "wind_mps":    return `${Number(v).toFixed(1)} m/s`;
    case "cloud_pct":   return `${Math.round(Number(v))}%`;
    default:            return String(v);
  }
}

export class DetailPanel {
  constructor({ root }) {
    this.root = root;
    this.dateEl = root.querySelector("#detail-date");
    this.metaEl = root.querySelector("#detail-meta");
    this.scoreEl = root.querySelector("#detail-score");
    this.scoreEmpty = root.querySelector("#detail-score-empty");
    this.statusEl = root.querySelector("#player-status");
    this.weatherEl = root.querySelector("#detail-weather");
    this.downloadsEl = root.querySelector("#detail-downloads");
    this.toggleEl = root.querySelector(".variant-toggle");
    this.playBtn = root.querySelector("#play-btn");
    this.progressEl = root.querySelector("#play-progress");
    this.timeEl = root.querySelector("#play-time");

    this.midi = null;
    this.scheduledIds = [];
    this.duration = 0;
    this.tickHandle = null;

    root.querySelector("#detail-close").addEventListener("click", () =>
      this.close()
    );
    root.addEventListener("click", (e) => {
      if (e.target === root) this.close();
    });
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

  open(song) {
    this.song = song;
    this.dateEl.textContent = formatDate(song.date);
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
      this.statusEl.textContent = "재생 준비 — 첫 재생 시 피아노 샘플 다운로드";
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
    this.statusEl.textContent = "피아노 샘플 로딩 중…";
    this.playBtn.disabled = true;
    await Tone.start();
    const piano = await getPiano();
    const pad   = getPad();

    Tone.Transport.stop();
    Tone.Transport.cancel(0);

    // schedule notes
    const t0 = 0.05;
    this.midi.tracks.forEach((track) => {
      const isHarmony = /harmony/i.test(track.name || "")
        || track.notes.some((n) => track.notes.filter(
          (x) => Math.abs(x.time - n.time) < 0.001).length >= 3);
      track.notes.forEach((note) => {
        const inst = isHarmony ? pad : piano;
        Tone.Transport.schedule((time) => {
          inst.triggerAttackRelease(
            note.name, note.duration, time, note.velocity * 0.85
          );
        }, t0 + note.time);
      });
    });

    Tone.Transport.scheduleOnce(() => this.stop(), t0 + this.duration + 1.5);

    Tone.Transport.start();
    this.playBtn.textContent = "■";
    this.playBtn.disabled = false;
    this.statusEl.textContent = "재생 중";
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
    if (!paths) return;
    for (const [key, label] of DOWNLOAD_KEYS) {
      const url = publicUrl(paths[key]);
      if (!url) continue;
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = url;
      a.download = "";
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
