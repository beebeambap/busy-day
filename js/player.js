import { publicUrl, recordPlay, updateSongNotes } from "./api.js";
import * as Tone from "https://esm.sh/tone@14.8.49";
import { Midi } from "https://esm.sh/@tonejs/midi@2.0.28";

// ── master output chain ─────────────────────────────────────────
// Web playback was too quiet vs. native apps (~-25 LUFS). We route
// everything through a master compressor + makeup gain + limiter so
// the perceived loudness lands closer to streaming-style mastering
// without ever clipping the speakers.
//
//   <every voice> → MASTER (compressor) → gain +10dB → limiter -0.5 → speakers
//
// `toMaster(node)` is a drop-in for the old `.toDestination()`.

let MASTER = null;
let _masterReady = false;

function _initMaster() {
  if (_masterReady) return;
  const comp = new Tone.Compressor({
    threshold: -18,
    ratio:     3,
    attack:    0.005,
    release:   0.18,
    knee:      6,
  });
  const makeup  = new Tone.Gain(Tone.dbToGain(10));
  const limiter = new Tone.Limiter(-0.5);
  comp.connect(makeup);
  makeup.connect(limiter);
  limiter.toDestination();
  MASTER = comp;
  _masterReady = true;
}
_initMaster();

function toMaster(node) {
  node.connect(MASTER);
  return node;
}

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

function _bowedStringSynth({ harmonicity, attack, sustain, release,
                              modAttack, modDecay, modSustain, modRelease,
                              volume, vibratoFreq, vibratoDepth }) {
  // Common bowed-string body: AMSynth voice with sawtooth carrier,
  // plus a master-rate vibrato LFO modulating detune for the breathing
  // characteristic of real strings.
  const synth = new Tone.PolySynth(Tone.AMSynth, {
    harmonicity,
    envelope: { attack, decay: 0.3, sustain, release },
    modulationEnvelope: {
      attack: modAttack, decay: modDecay,
      sustain: modSustain, release: modRelease,
    },
  });
  synth.volume.value = volume;
  if (vibratoFreq && vibratoDepth) {
    const vib = new Tone.LFO({
      frequency: vibratoFreq,
      type: "sine",
      min: -vibratoDepth,
      max: +vibratoDepth,
    }).start();
    vib.connect(synth.detune);
  }
  return synth;
}

function makeViolin(volume) {
  // Bright, fast vibrato. Sits one octave above viola.
  return _bowedStringSynth({
    harmonicity: 2,
    attack: 0.18, sustain: 0.85, release: 1.0,
    modAttack: 0.2, modDecay: 0.2, modSustain: 0.7, modRelease: 0.8,
    vibratoFreq: 5.5, vibratoDepth: 8,   // ±8 cents
    volume,
  });
}

function makeViola(volume) {
  // Warmer mid-range body, mellower vibrato.
  return _bowedStringSynth({
    harmonicity: 1.5,
    attack: 0.30, sustain: 0.85, release: 1.4,
    modAttack: 0.3, modDecay: 0.2, modSustain: 0.7, modRelease: 1.0,
    vibratoFreq: 4.5, vibratoDepth: 6,
    volume,
  });
}

function makeCello(volume) {
  // Deep, slow bow, generous resonance.
  return _bowedStringSynth({
    harmonicity: 1,
    attack: 0.45, sustain: 0.85, release: 1.8,
    modAttack: 0.4, modDecay: 0.3, modSustain: 0.7, modRelease: 1.4,
    vibratoFreq: 3.5, vibratoDepth: 5,
    volume,
  });
}

// Backward-compatible: existing rows with instrument_id="strings" still
// resolve through this. New rows use violin/viola/cello.
function makeStrings(volume) {
  return makeViola(volume);
}

function makeMusicBox(volume) {
  // Bell-like FM with inharmonic ratio (3.01) so it rings rather than
  // hums. Construction kept minimal because Tone.PolySynth in v14 has
  // known quirks propagating nested oscillator/modulation options into
  // each voice. We pass only flat options + envelopes and set the
  // master volume on the synth's own .volume.value.
  const synth = new Tone.PolySynth(Tone.FMSynth, {
    harmonicity: 3.01,
    modulationIndex: 14,
    envelope: { attack: 0.002, decay: 1.8, sustain: 0.05, release: 1.8 },
    modulationEnvelope: {
      attack: 0.005, decay: 0.6, sustain: 0.0, release: 0.4,
    },
  });
  synth.volume.value = volume;
  return synth;
}

function makeHorn(volume) {
  // Soft brass — gentle attack, full mid-range body
  return new Tone.PolySynth(Tone.FMSynth, {
    harmonicity: 1,
    modulationIndex: 3,
    oscillator: { type: "sine" },
    envelope:   { attack: 0.18, decay: 0.4, sustain: 0.75, release: 0.9 },
    modulation: { type: "triangle" },
    modulationEnvelope: {
      attack: 0.22, decay: 0.4, sustain: 0.6, release: 0.5 },
    volume,
  });
}

// instrument_id (user override) -> factory(reverbBus) returning the
// melody synth already routed to the bus. Returning null = no override,
// fall back to the genre-derived melody.
// Each factory MUST return the synth itself (never a downstream node)
// because Tone's `connect` returns the source in v14 but tooling
// changes have bitten us before. Be explicit.
const INSTRUMENT_FACTORIES = {
  piano:     (reverb) => { const s = makePiano(2.4, -4); s.connect(reverb); return s; },
  rhodes:    (reverb) => { const s = makeRhodes(-10);    s.connect(reverb); return s; },
  nylon:     (reverb) => { const s = makeNylon(-8);      s.connect(reverb); return s; },
  violin:    (reverb) => { const s = makeViolin(-10);    s.connect(reverb); return s; },
  viola:     (reverb) => { const s = makeViola(-9);      s.connect(reverb); return s; },
  cello:     (reverb) => { const s = makeCello(-8);      s.connect(reverb); return s; },
  strings:   (reverb) => { const s = makeStrings(-10);   s.connect(reverb); return s; },
  music_box: (reverb) => { const s = makeMusicBox(-4);   s.connect(reverb); return s; },
  horn:      (reverb) => { const s = makeHorn(-10);      s.connect(reverb); return s; },
};

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

function makeDrone(volume) {
  // Two detuned sines an octave apart — fog under the mix.
  const out = new Tone.Gain(1);
  const a = new Tone.Oscillator({ frequency: "C1", type: "sine" });
  const b = new Tone.Oscillator({ frequency: "C2", type: "sine", detune: 4 });
  const filt = new Tone.Filter({ frequency: 280, type: "lowpass", Q: 0.4 });
  const gain = new Tone.Gain(Tone.dbToGain(volume)).connect(out);
  a.connect(filt); b.connect(filt); filt.connect(gain);
  // Polyphonic-ish facade: we expose triggerAttackRelease(note) and
  // retune the oscillators on each call so the IR's drone events
  // (one per section) actually retune the underlying drone.
  return {
    _a: a, _b: b, _gain: gain, _started: false,
    output: out,
    triggerAttackRelease(note, _dur, time, velocity = 0.7) {
      const freq = Tone.Frequency(note).toFrequency();
      a.frequency.setValueAtTime(freq, time);
      b.frequency.setValueAtTime(freq * 2, time);
      if (!this._started) {
        a.start(time); b.start(time);
        this._started = true;
      }
      // gentle level envelope synced to the section
      gain.gain.cancelAndHoldAtTime(time);
      gain.gain.setValueAtTime(gain.gain.value, time);
      gain.gain.linearRampToValueAtTime(
        Tone.dbToGain(volume) * velocity, time + 1.5,
      );
    },
    dispose() {
      try { a.stop(); b.stop(); } catch {}
      a.dispose(); b.dispose(); filt.dispose(); gain.dispose(); out.dispose();
    },
  };
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

// ── percussion rack ────────────────────────────────────────────
//
// Returns an object with .trigger(kind, time, velocity). Each voice
// is intentionally low-volume — percussion is rhythmic skeleton, not
// a featured layer. Routed dry (no reverb) so the pulse stays crisp.

function makePercussion() {
  const out = toMaster(new Tone.Gain(0.85));

  const tap = new Tone.MembraneSynth({
    pitchDecay: 0.005,
    octaves: 1.5,
    oscillator: { type: "sine" },
    envelope: { attack: 0.001, decay: 0.10, sustain: 0, release: 0.08 },
    volume: -14,
  }).connect(out);

  const shaker = new Tone.NoiseSynth({
    noise:    { type: "white" },
    envelope: { attack: 0.001, decay: 0.05, sustain: 0, release: 0.02 },
    volume: -22,
  }).connect(out);

  const brush = new Tone.NoiseSynth({
    noise:    { type: "pink" },
    envelope: { attack: 0.005, decay: 0.18, sustain: 0, release: 0.06 },
    volume: -20,
  }).connect(out);

  const ride = new Tone.MetalSynth({
    frequency: 250,
    harmonicity: 4.1,
    modulationIndex: 12,
    resonance: 4000,
    octaves: 1,
    envelope: { attack: 0.001, decay: 0.4, release: 0.3 },
    volume: -34,
  }).connect(out);

  const kick = new Tone.MembraneSynth({
    pitchDecay: 0.04,
    octaves: 6,
    oscillator: { type: "sine" },
    envelope: { attack: 0.001, decay: 0.4, sustain: 0, release: 1.2 },
    volume: -10,
  }).connect(out);

  const snare = new Tone.NoiseSynth({
    noise:    { type: "white" },
    envelope: { attack: 0.001, decay: 0.18, sustain: 0, release: 0.08 },
    volume: -16,
  }).connect(out);

  const hat = new Tone.MetalSynth({
    frequency: 200,
    harmonicity: 5.1,
    modulationIndex: 20,
    resonance: 4000,
    octaves: 1.5,
    envelope: { attack: 0.001, decay: 0.05, release: 0.02 },
    volume: -32,
  }).connect(out);

  return {
    trigger(kind, time, velocity = 0.7) {
      switch (kind) {
        case "tap":
          tap.triggerAttackRelease("C3", "32n", time, velocity);
          break;
        case "shaker":
          shaker.triggerAttackRelease("32n", time, velocity);
          break;
        case "brush":
          brush.triggerAttackRelease("16n", time, velocity * 0.85);
          break;
        case "ride":
          ride.triggerAttackRelease("32n", time, velocity * 0.8);
          break;
        case "kick":
          kick.triggerAttackRelease("C1", "8n", time, velocity);
          break;
        case "snare":
          snare.triggerAttackRelease("16n", time, velocity);
          break;
        case "hat":
          hat.triggerAttackRelease("32n", time, velocity * 0.7);
          break;
      }
    },
  };
}

const _instruments = new Map(); // cache key -> { melody, harmony, bass, percussion, reverb, ready }

// ── ambience layer (synthesized weather sounds) ──────────────────
//
// Pure function of weather + features. No external samples; everything
// is built from Tone.js primitives so the layer ships with the page.
// Voices are routed dry (no reverb) because rain/wind on top of the
// already-reverbed instruments would mush.

function _clip01(x) { return Math.max(0, Math.min(1, x)); }

export function decideAmbience(weather, features) {
  const w        = weather  || {};
  const f        = features || {};
  const pcp      = Number(w.precip_mm ?? 0);
  const wind     = Number(w.wind_mps  ?? 0);
  const tempC    = Number(w.temp_c    ?? 15);
  const humidity = Number(w.humidity  ?? 60);
  const bright   = Number(f.brightness ?? 0.5);
  const warm     = Number(f.warmth     ?? 0.5);

  const layers = [];

  if (pcp > 0.1) {
    const intensity = _clip01(pcp / 10.0);
    layers.push({
      type: "rain",
      volume_db: round1(-34 + _clip01(pcp / 20) * 20),
      intensity,
    });
  }

  if (wind > 4.0) {
    layers.push({
      type: "wind",
      volume_db: round1(-36 + _clip01((wind - 4) / 8) * 20),
      intensity: _clip01(wind / 12),
    });
  }

  if (bright > 0.7 && warm > 0.5 && pcp < 0.5) {
    layers.push({
      type: "birds",
      volume_db: -28,
      density: _clip01(bright),
    });
  }

  if (tempC < 3.0) {
    layers.push({ type: "indoor", volume_db: -30 });
  }

  if (humidity > 80 && wind < 3.0) {
    layers.push({
      type: "hum",
      volume_db: -34,
      intensity: _clip01((humidity - 80) / 20),
    });
  }

  return layers;
}

export function reverbWetFromHumidity(humidity) {
  const h = Number(humidity ?? 60);
  return round2(0.20 + _clip01((h - 30) / 60) * 0.40);
}

function round1(x) { return Math.round(x * 10) / 10; }
function round2(x) { return Math.round(x * 100) / 100; }

function _makeRain(volumeDb, intensity = 0.5) {
  const noise = new Tone.Noise("pink");
  const filt = new Tone.Filter({
    frequency: 1200 + intensity * 2200,
    type: "lowpass",
    rolloff: -24,
    Q: 0.5,
  });
  const gain = toMaster(new Tone.Gain(0));
  noise.chain(filt, gain);
  noise.start();
  gain.gain.rampTo(Tone.dbToGain(volumeDb), 1.5);
  return {
    dispose() {
      gain.gain.rampTo(0, 0.6);
      setTimeout(() => {
        try { noise.stop(); } catch {}
        noise.dispose(); filt.dispose(); gain.dispose();
      }, 700);
    },
  };
}

function _makeWind(volumeDb, intensity = 0.5) {
  const noise = new Tone.Noise("brown");
  const filt = new Tone.Filter({
    frequency: 600, type: "bandpass", Q: 0.4,
  });
  const lfo = new Tone.LFO({
    frequency: 0.15 + intensity * 0.2, min: 200, max: 1500, type: "sine",
  });
  lfo.connect(filt.frequency);
  const gain = toMaster(new Tone.Gain(0));
  noise.chain(filt, gain);
  noise.start();
  lfo.start();
  gain.gain.rampTo(Tone.dbToGain(volumeDb), 2);
  return {
    dispose() {
      gain.gain.rampTo(0, 0.8);
      setTimeout(() => {
        try { noise.stop(); lfo.stop(); } catch {}
        noise.dispose(); filt.dispose(); lfo.dispose(); gain.dispose();
      }, 900);
    },
  };
}

function _makeBirds(volumeDb, density = 0.35) {
  const synth = new Tone.FMSynth({
    harmonicity: 12,
    modulationIndex: 5,
    envelope:   { attack: 0.001, decay: 0.07, sustain: 0, release: 0.06 },
    modulation: { type: "sine" },
    modulationEnvelope: {
      attack: 0.001, decay: 0.06, sustain: 0, release: 0.05,
    },
    volume: volumeDb,
  });
  toMaster(synth);

  const NOTES = ["A6", "B6", "C7", "D7", "E7", "G7"];
  const loop = new Tone.Loop((time) => {
    if (Math.random() < density * 0.35) {
      const note = NOTES[Math.floor(Math.random() * NOTES.length)];
      synth.triggerAttackRelease(note, "32n", time, 0.6 + Math.random() * 0.3);
      if (Math.random() < 0.4) {
        synth.triggerAttackRelease(note, "32n", time + 0.08, 0.5);
      }
    }
  }, "8n");
  loop.start(0);

  return {
    dispose() {
      try { loop.stop(); } catch {}
      loop.dispose(); synth.dispose();
    },
  };
}

function _makeIndoor(volumeDb) {
  const drone = new Tone.Oscillator(46, "sine"); // ~A#1
  const noise = new Tone.Noise("brown");
  const filt  = new Tone.Filter({ frequency: 350, type: "lowpass" });
  const gain  = toMaster(new Tone.Gain(0));
  drone.connect(gain);
  noise.connect(filt); filt.connect(gain);
  drone.start(); noise.start();
  gain.gain.rampTo(Tone.dbToGain(volumeDb), 2);
  return {
    dispose() {
      gain.gain.rampTo(0, 0.8);
      setTimeout(() => {
        try { drone.stop(); noise.stop(); } catch {}
        drone.dispose(); noise.dispose(); filt.dispose(); gain.dispose();
      }, 900);
    },
  };
}

function _makeHum(volumeDb) {
  const a = new Tone.Oscillator(41, "sine"); // E1
  const b = new Tone.Oscillator(48, "sine"); // C2
  const gain = toMaster(new Tone.Gain(0));
  a.connect(gain); b.connect(gain);
  a.start(); b.start();
  gain.gain.rampTo(Tone.dbToGain(volumeDb), 2.5);
  return {
    dispose() {
      gain.gain.rampTo(0, 1.0);
      setTimeout(() => {
        try { a.stop(); b.stop(); } catch {}
        a.dispose(); b.dispose(); gain.dispose();
      }, 1100);
    },
  };
}

const AMB_FACTORIES = {
  rain:   (l) => _makeRain  (l.volume_db, l.intensity),
  wind:   (l) => _makeWind  (l.volume_db, l.intensity),
  birds:  (l) => _makeBirds (l.volume_db, l.density),
  indoor: (l) => _makeIndoor(l.volume_db),
  hum:    (l) => _makeHum   (l.volume_db),
};

let _ambVoices = [];

function startAmbience(layers) {
  stopAmbience();
  for (const l of layers) {
    const f = AMB_FACTORIES[l.type];
    if (!f) continue;
    try { _ambVoices.push(f(l)); }
    catch (err) { console.warn("[ambience] failed:", l.type, err); }
  }
}

function stopAmbience() {
  for (const v of _ambVoices) {
    try { v.dispose(); } catch {}
  }
  _ambVoices = [];
}

function buildInstruments(genre, instrumentId) {
  const reverb = toMaster(new Tone.Reverb({ decay: 3.6, wet: 0.34 }));
  const ready  = [reverb.generate()];
  let needsSamples = false;       // becomes true if any voice uses Salamander

  let melody, harmony, bass;

  // ── melody. User override wins outright; otherwise genre-default.
  if (instrumentId && INSTRUMENT_FACTORIES[instrumentId]) {
    melody = INSTRUMENT_FACTORIES[instrumentId](reverb);
    if (instrumentId === "piano") needsSamples = true;
  } else if (genre === "jazz_ballad") {
    melody = makeRhodes(-10).connect(reverb);
  } else if (genre === "bossa_nova") {
    melody = makeNylon(-8).connect(reverb);
  } else {
    // ambient / neo_classical / folk / lo_fi : piano-led
    const release = PIANO_RELEASE[genre] ?? 2.0;
    const isLoFi  = genre === "lo_fi";
    melody = makePiano(release, isLoFi ? -8 : -4);
    if (isLoFi) {
      const lp = new Tone.Filter({
        frequency: 2400, type: "lowpass", rolloff: -12,
      });
      melody.connect(lp); lp.connect(reverb);
    } else {
      melody.connect(reverb);
    }
    needsSamples = true;
  }

  // ── harmony per genre.
  if (genre === "jazz_ballad") {
    harmony = makeRhodes(-18).connect(reverb);
  } else if (genre === "bossa_nova") {
    harmony = makeNylon(-14).connect(reverb);
  } else if (genre === "neo_classical") {
    harmony = makeStringPad(-18).connect(reverb);
  } else {
    harmony = makeAMPad(-22).connect(reverb);
  }

  // ── bass per genre.
  if (genre === "jazz_ballad") {
    bass = toMaster(makeUprightBass(-12));
  } else if (genre === "bossa_nova") {
    bass = toMaster(makeUprightBass(-10));
  } else {
    const release = PIANO_RELEASE[genre] ?? 2.0;
    bass = toMaster(makePiano(release * 0.7, -10));
    needsSamples = true;
  }

  if (needsSamples) ready.push(Tone.loaded());

  const percussion = makePercussion();
  // The drone is built lazily — only attached if the song's IR actually
  // has drone events. Voice itself is always available so swapping
  // between cloudy / clear songs without recreating the cache works.
  const drone = makeDrone(-22);
  drone.output.connect(reverb);

  return {
    melody, harmony, bass, percussion, drone, reverb,
    ready: Promise.all(ready),
  };
}

async function getInstruments(genre, instrumentId, reverbWet = null) {
  const key = `${genre}::${instrumentId || ""}`;
  let cached = _instruments.get(key);
  if (!cached) {
    cached = buildInstruments(genre, instrumentId || null);
    _instruments.set(key, cached);
  }
  await cached.ready;
  // Per-song reverb adjustment (humidity-driven). Smooth ramp so it
  // doesn't click when swapping variants.
  if (cached.reverb && reverbWet != null) {
    cached.reverb.wet.rampTo(reverbWet, 0.5);
  }
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

function _kstHHMMTag(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  // KST regardless of viewer timezone. Colon is not filename-safe so
  // we render HH-MM with a hyphen.
  const kst = new Date(d.getTime() + 9 * 3600 * 1000);
  const hh = String(kst.getUTCHours()).padStart(2, "0");
  const mm = String(kst.getUTCMinutes()).padStart(2, "0");
  return `${hh}-${mm}`;
}

function buildDownloadName(song, suffix) {
  const date    = song.date || "song";
  const time    = _kstHHMMTag(song.created_at);
  const weather = _weatherTag(song.weather);
  const genre   = _slug(song.genre);
  const parts = ["busy-day", date, time, weather, genre]
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
  // situational
  dawn:       "새벽",
  commute:    "출근길",
  nap:        "낮잠",
  focus:      "작업 중",
  walk:       "산책",
};

const INSTRUMENT_LABELS = {
  piano:     "피아노",
  rhodes:    "EP",
  nylon:     "기타",
  strings:   "현악",
  music_box: "음악상자",
  horn:      "호른",
};

function variantLabel(song) {
  if (song.variant_id === "auto") return "오늘";
  const parts = [];
  if (song.intent_id && INTENT_LABELS[song.intent_id]) {
    parts.push(INTENT_LABELS[song.intent_id]);
  }
  if (song.instrument_id && INSTRUMENT_LABELS[song.instrument_id]) {
    parts.push(INSTRUMENT_LABELS[song.instrument_id]);
  }
  return parts.length ? parts.join(" · ") : song.variant_id;
}

export class DetailPanel {
  constructor({ root }) {
    this.root        = root;
    this.dateEl      = root.querySelector("#detail-date");
    this.metaEl      = root.querySelector("#detail-meta");
    this.createdEl   = root.querySelector("#detail-created");
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
    this.titleInput  = root.querySelector("#detail-title");
    this.notesInput  = root.querySelector("#detail-notes");
    this.memoStatus  = root.querySelector("#detail-memo-status");

    this.midi = null;
    this.duration = 0;
    this.tickHandle = null;
    this._memoTimer = null;
    this._memoLast  = "";

    this.titleInput.addEventListener("input",  () => this._scheduleMemoSave());
    this.titleInput.addEventListener("blur",   () => this._flushMemoSave());
    this.notesInput.addEventListener("input",  () => this._scheduleMemoSave());
    this.notesInput.addEventListener("blur",   () => this._flushMemoSave());

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
    this._flushMemoSave();           // commit any unsaved typing
    this.song = song;
    this.variants = variants && variants.length ? variants : [song];
    this.dateEl.textContent = formatDate(song.date);
    this.metaEl.textContent = fmtMeta(song);
    this.createdEl.textContent = formatCreated(song.created_at, song.variant_id);
    this.renderVariantChips();
    this.renderMemo(song);

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
    const instrumentId = this.song?.instrument_id || null;
    const reverbWet = reverbWetFromHumidity(this.song?.weather?.humidity);
    const { melody, harmony, bass, percussion, drone } =
      await getInstruments(genre, instrumentId, reverbWet);

    // Ambience layers — derived purely from weather + features so they
    // stay reproducible. Started here so they begin on the same gesture
    // that started Tone.Transport (browsers require this).
    const ambLayers = decideAmbience(this.song?.weather, this.song?.features);
    startAmbience(ambLayers);

    Tone.Transport.stop();
    Tone.Transport.cancel(0);

    const t0 = 0.05;
    this.midi.tracks.forEach((track) => {
      const name = (track.name || "").toLowerCase();
      const isDrum = (track.channel === 9) || name.includes("percussion");

      if (isDrum) {
        // GM percussion (channel 9). Look up our internal kind by note.
        const NOTE_TO_KIND = {
          75: "tap", 70: "shaker", 39: "brush", 51: "ride",
          36: "kick", 38: "snare", 42: "hat",
        };
        track.notes.forEach((note) => {
          const kind = NOTE_TO_KIND[note.midi];
          if (!kind) return;
          Tone.Transport.schedule((time) => {
            percussion.trigger(kind, time, note.velocity * 0.95);
          }, t0 + note.time);
        });
        return;
      }

      let inst;
      if (name.includes("harmony"))    inst = harmony;
      else if (name.includes("bass"))  inst = bass;
      else if (name.includes("drone")) inst = drone;
      else                             inst = melody;

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
    stopAmbience();
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
    this._flushMemoSave();
    this.stop();
    this.song = song;
    this.metaEl.textContent = fmtMeta(song);
    this.createdEl.textContent = formatCreated(song.created_at, song.variant_id);
    this.renderMemo(song);

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

  // ── memo (title + notes) ──────────────────────────────────────
  renderMemo(song) {
    this.titleInput.value = song?.title || "";
    this.notesInput.value = song?.notes || "";
    this._memoLast = this._memoSnapshot();
    if (song?.notes_updated_at) {
      this.memoStatus.textContent = `${formatRelative(song.notes_updated_at)} 저장됨`;
    } else {
      this.memoStatus.textContent = "메모는 자동 저장됩니다";
    }
  }

  _memoSnapshot() {
    return JSON.stringify({
      title: this.titleInput.value, notes: this.notesInput.value,
    });
  }

  _scheduleMemoSave() {
    if (!this.song) return;
    if (this._memoTimer) clearTimeout(this._memoTimer);
    this.memoStatus.textContent = "저장 중…";
    this._memoTimer = setTimeout(() => this._flushMemoSave(), 1500);
  }

  async _flushMemoSave() {
    if (this._memoTimer) {
      clearTimeout(this._memoTimer);
      this._memoTimer = null;
    }
    if (!this.song) return;
    const snap = this._memoSnapshot();
    if (snap === this._memoLast) return;     // no change
    const songId = this.song.id;
    try {
      const updated = await updateSongNotes(songId, {
        title: this.titleInput.value,
        notes: this.notesInput.value,
      });
      this._memoLast = snap;
      if (this.song && this.song.id === songId && updated) {
        this.song.title = updated.title;
        this.song.notes = updated.notes;
        this.song.notes_updated_at = updated.notes_updated_at;
        this.memoStatus.textContent = "방금 저장됨";
      }
    } catch (err) {
      console.error("[memo] save failed:", err);
      this.memoStatus.textContent = "저장 실패";
    }
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
      const filename = buildDownloadName(this.song, suffix);
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.title = filename;
      a.textContent = label;

      // Hybrid: binary downloads (mid/wav/mp3/musicxml) intercept with
      // fetch+blob so the saved filename matches our naming. View-
      // friendly assets (svg/json) keep the native click so the
      // browser opens them in a tab — that was the user's preferred
      // behaviour for previewable formats.
      const ext = (suffix.split(".").pop() || "").toLowerCase();
      const FORCE_DOWNLOAD = new Set(["mid", "midi", "wav", "mp3", "musicxml"]);

      if (FORCE_DOWNLOAD.has(ext)) {
        a.addEventListener("click", (e) => {
          e.preventDefault();
          downloadAsBlob(url, filename).catch((err) => {
            console.warn("[download] blob failed:", err);
            window.open(url, "_blank");
          });
        });
      } else {
        a.target = "_blank";
        a.rel = "noopener";
      }

      li.appendChild(a);
      this.downloadsEl.appendChild(li);
    }
  }
}

async function downloadAsBlob(url, filename) {
  const r = await fetch(url, { mode: "cors", credentials: "omit" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const blob = await r.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(objUrl);
    a.remove();
  }, 1000);
}

function formatDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const month = date.toLocaleString("en-US", { month: "long" });
  return `${month} ${d}, ${y}`;
}

function formatCreated(iso, variantId) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  // Always render in KST regardless of viewer timezone.
  const kst = new Date(d.getTime() + 9 * 3600 * 1000);
  const Y = kst.getUTCFullYear();
  const M = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const D = String(kst.getUTCDate()).padStart(2, "0");
  const hh = String(kst.getUTCHours()).padStart(2, "0");
  const mm = String(kst.getUTCMinutes()).padStart(2, "0");
  const tag = variantId === "auto" ? "자동" : "수동";
  return `${tag}  ${Y}.${M}.${D} ${hh}:${mm} KST 생성`;
}

function formatRelative(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60)    return "방금";
  if (diff < 3600)  return `${Math.round(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.round(diff / 3600)}시간 전`;
  return `${Math.round(diff / 86400)}일 전`;
}
