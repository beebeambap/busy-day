"""IR -> standard MIDI file via mido.

Phase 1 emits MIDI only. Phase 2 will add MusicXML (music21) and audio
rendering (FluidSynth -> WAV -> MP3 via ffmpeg).
"""

from __future__ import annotations

from random import Random

import mido

from .comping import GM_DRUM_NOTE

TICKS_PER_BEAT = 480
PERC_NOTE_LEN_BEATS = 0.08    # short stab so the drum note doesn't sustain

# ── acoustic salt (anti-fingerprint-collision) ──────────────────────
# Audio fingerprinters (ACRCloud / Content ID) hash time-frequency
# spectral peaks. Ambient music concentrates energy in a narrow
# register with repetitive chord progressions, so different songs can
# produce near-identical fingerprints and trip false-positive matches.
#
# We bake a tiny, deterministic, per-song "salt" into the MIDI:
#   - global micro-detune  (±12..30 cents) → shifts every spectral peak
#     off the standard tuning grid where reference tracks sit
#   - tempo micro-jitter    (±1.5%)         → shifts the onset-interval
#     hashes on the time axis
# Both are sub-perceptual (a quarter-tone is 50 cents; 1.5% tempo is
# inaudible) but together they move the fingerprint on BOTH axes, which
# is what breaks exact-match landmark hashing. Derived from the song
# seed so re-rendering is reproducible yet unique per (date, city).
_SALT_XOR = 0xACE5A17


def acoustic_salt(seed: int) -> tuple[float, int]:
    """Return (tempo_factor, detune_cents) for a song seed."""
    rng = Random(seed ^ _SALT_XOR)
    tempo_factor = 1.0 + rng.uniform(-0.015, 0.015)
    mag = rng.uniform(12.0, 30.0)
    detune_cents = int(round(mag if rng.random() < 0.5 else -mag))
    return tempo_factor, detune_cents


def _append_detune(track: "mido.MidiTrack", channel: int, cents: int) -> None:
    """Set channel pitch-bend range to ±2 semitones (RPN 0) then apply a
    static pitch bend equal to `cents`. All notes on the channel inherit
    the bend → a uniform global detune (no chorusing, inaudible)."""
    if cents == 0:
        return
    cc = lambda c, v: mido.Message("control_change", channel=channel,
                                   control=c, value=v, time=0)
    # RPN 0,0 = pitch-bend sensitivity; data entry = 2 semitones
    track.append(cc(101, 0)); track.append(cc(100, 0))
    track.append(cc(6, 2));   track.append(cc(38, 0))
    # close RPN so later data-entry CCs can't drift the setting
    track.append(cc(101, 127)); track.append(cc(100, 127))
    bend = max(-8192, min(8191, round(cents / 200.0 * 8192)))
    track.append(mido.Message("pitchwheel", channel=channel,
                              pitch=bend, time=0))

# General MIDI program numbers (0-indexed) per genre & track
GM_PROGRAMS = {
    "ambient":       {"melody": 0,  "harmony": 88, "bass": 32},  # piano + new-age pad + ac. bass
    "bossa_nova":    {"melody": 0,  "harmony": 24, "bass": 32},  # piano + nylon + ac. bass
    "jazz_ballad":   {"melody": 0,  "harmony": 4,  "bass": 32},  # piano + epiano + ac. bass
    "lo_fi":         {"melody": 4,  "harmony": 89, "bass": 33},  # epiano + warm pad + finger bass
    "neo_classical": {"melody": 0,  "harmony": 48, "bass": 42},  # piano + strings + cello
    "folk":          {"melody": 0,  "harmony": 24, "bass": 32},  # piano + nylon + ac. bass
}


def _events_to_messages(
    events: list[dict],
    channel: int,
    bpb: float,
) -> list[tuple[int, mido.Message]]:
    """Returns list of (absolute_tick, msg) for note_on + note_off."""
    out = []
    for ev in events:
        start = (ev["bar"] * bpb + ev["start_beat"]) * TICKS_PER_BEAT
        dur   = ev["dur_beats"] * TICKS_PER_BEAT
        if "pitch" in ev:
            pitches = [ev["pitch"]]
        else:
            pitches = ev["pitches"]
        vel = max(1, min(127, int(ev.get("vel", 64))))
        for p in pitches:
            out.append((int(start),
                        mido.Message("note_on", channel=channel,
                                     note=int(p), velocity=vel)))
            out.append((int(start + dur),
                        mido.Message("note_off", channel=channel,
                                     note=int(p), velocity=0)))
    return out


def _track_with_program(name: str, program: int, channel: int) -> mido.MidiTrack:
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name=name, time=0))
    tr.append(mido.Message("program_change", channel=channel,
                           program=program, time=0))
    return tr


def _flush_track(tr: mido.MidiTrack, abs_msgs: list[tuple[int, mido.Message]]) -> None:
    abs_msgs.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))
    last = 0
    for t, msg in abs_msgs:
        delta = max(0, t - last)
        tr.append(msg.copy(time=delta))
        last = t


def _pedal_messages(
    pedals: list[dict], channel: int, bpb: float,
) -> list[tuple[int, mido.Message]]:
    out = []
    for seg in pedals:
        on_t  = (seg["from_bar"] * bpb + seg["on"])  * TICKS_PER_BEAT
        off_t = (seg["to_bar"]   * bpb + seg["off"]) * TICKS_PER_BEAT
        out.append((int(on_t),
                    mido.Message("control_change", channel=channel,
                                 control=64, value=127)))
        out.append((int(off_t),
                    mido.Message("control_change", channel=channel,
                                 control=64, value=0)))
    return out


def render_midi(ir: dict, path: str) -> None:
    spec = ir["spec"]
    bpm = spec["bpm"]
    genre = spec["genre"]
    bpb = float(spec["meter"].split("/")[0])
    programs = dict(GM_PROGRAMS.get(genre, GM_PROGRAMS["ambient"]))

    # Optional user instrument override for the melody track only.
    inst_program = ir.get("melody_gm_program")
    if inst_program is not None:
        programs["melody"] = int(inst_program)

    pedals = ir.get("pedals", [])

    # Per-song acoustic salt: sub-perceptual detune + tempo jitter so the
    # rendered audio's fingerprint sits off the standard grid (see
    # acoustic_salt docstring). Seed comes from the IR meta.
    seed = int(ir.get("meta", {}).get("seed", 0))
    tempo_factor, detune_cents = acoustic_salt(seed)
    salted_bpm = bpm * tempo_factor

    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)

    # tempo + meter on track 0
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo",
                                 tempo=mido.bpm2tempo(salted_bpm), time=0))
    n, d = (int(x) for x in spec["meter"].split("/"))
    meta.append(mido.MetaMessage("time_signature",
                                 numerator=n, denominator=d, time=0))
    meta.append(mido.MetaMessage("track_name",
                                 name=f"busy day {ir['meta']['date']}", time=0))
    mid.tracks.append(meta)

    # melody (with sustain pedal CC64 on the same channel)
    mel = _track_with_program("melody", programs["melody"], channel=0)
    _append_detune(mel, channel=0, cents=detune_cents)
    mel_msgs = _events_to_messages(ir["tracks"]["melody"], channel=0, bpb=bpb)
    mel_msgs += _pedal_messages(pedals, channel=0, bpb=bpb)
    _flush_track(mel, mel_msgs)
    mid.tracks.append(mel)

    # harmony (also pedaled to keep pad legato across chord changes)
    har = _track_with_program("harmony", programs["harmony"], channel=1)
    _append_detune(har, channel=1, cents=detune_cents)
    har_msgs = _events_to_messages(ir["tracks"]["harmony"], channel=1, bpb=bpb)
    har_msgs += _pedal_messages(pedals, channel=1, bpb=bpb)
    _flush_track(har, har_msgs)
    mid.tracks.append(har)

    # bass (no pedal — would muddy the low register)
    bas = _track_with_program("bass", programs["bass"], channel=2)
    _append_detune(bas, channel=2, cents=detune_cents)
    _flush_track(bas,
                 _events_to_messages(ir["tracks"]["bass"], channel=2, bpb=bpb))
    mid.tracks.append(bas)

    # percussion on GM drum channel 9. No program_change needed; the
    # GM standard fixes the kit to channel 10 (1-indexed = 9 here).
    perc_events = ir.get("tracks", {}).get("percussion", [])
    if perc_events:
        perc = mido.MidiTrack()
        perc.append(mido.MetaMessage("track_name", name="percussion", time=0))
        msgs = []
        for ev in perc_events:
            note = GM_DRUM_NOTE.get(ev["kind"])
            if note is None:
                continue
            start_tick = int((ev["bar"] * bpb + ev["start_beat"])
                             * TICKS_PER_BEAT)
            end_tick   = int(start_tick + PERC_NOTE_LEN_BEATS * TICKS_PER_BEAT)
            vel = max(1, min(127, int(ev.get("vel", 64))))
            msgs.append((start_tick,
                         mido.Message("note_on", channel=9,
                                      note=note, velocity=vel)))
            msgs.append((end_tick,
                         mido.Message("note_off", channel=9,
                                      note=note, velocity=0)))
        _flush_track(perc, msgs)
        mid.tracks.append(perc)

    # drone (cloudy-day fog layer). One sustained low pitch per section
    # on its own channel + program (GM 88 = New Age Pad).
    drone_events = ir.get("tracks", {}).get("drone", [])
    if drone_events:
        dr = _track_with_program("drone", program=88, channel=3)
        _flush_track(
            dr,
            _events_to_messages(drone_events, channel=3, bpb=bpb),
        )
        mid.tracks.append(dr)

    mid.save(path)
