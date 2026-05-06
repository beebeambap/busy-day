import { publicUrl, recordPlay } from "./api.js";

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
  ["mp3_short", "MP3 1분"],
  ["mp3_long",  "MP3 2분+"],
  ["wav_short", "WAV 1분"],
  ["wav_long",  "WAV 2분+"],
  ["jpg",       "악보 JPG"],
  ["musicxml",  "MusicXML"],
  ["midi",      "MIDI"],
];

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
    this.scoreImg = root.querySelector("#detail-score");
    this.scoreEmpty = root.querySelector("#detail-score-empty");
    this.audio = root.querySelector("#detail-audio");
    this.weatherEl = root.querySelector("#detail-weather");
    this.downloadsEl = root.querySelector("#detail-downloads");
    this.toggleEl = root.querySelector(".variant-toggle");

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
      const v = btn.dataset.variant;
      this.setVariant(v);
    });
  }

  open(song) {
    this.song = song;
    this.dateEl.textContent = formatDate(song.date);
    this.metaEl.textContent = fmtMeta(song);

    const jpg = publicUrl(song.paths?.jpg);
    if (jpg) {
      this.scoreImg.src = jpg;
      this.scoreImg.hidden = false;
      this.scoreEmpty.hidden = true;
    } else {
      this.scoreImg.removeAttribute("src");
      this.scoreImg.hidden = true;
      this.scoreEmpty.hidden = false;
    }

    this.renderWeather(song.weather);
    this.renderDownloads(song.paths);
    this.setVariant("short");

    this.root.hidden = false;
    this.root.setAttribute("aria-hidden", "false");
  }

  close() {
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.root.hidden = true;
    this.root.setAttribute("aria-hidden", "true");
  }

  setVariant(v) {
    for (const btn of this.toggleEl.querySelectorAll("button")) {
      btn.classList.toggle("active", btn.dataset.variant === v);
    }
    const key = v === "long" ? "mp3_long" : "mp3_short";
    const url = publicUrl(this.song?.paths?.[key]);
    const wasPlaying = !this.audio.paused;
    if (url) {
      this.audio.src = url;
      this.audio.load();
      if (wasPlaying) this.audio.play().catch(() => {});
    } else {
      this.audio.removeAttribute("src");
    }
    this.variant = v;
    this.audio.onplay = () => {
      if (this.song) recordPlay(this.song.id, this.variant).catch(() => {});
    };
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
