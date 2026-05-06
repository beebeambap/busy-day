"""IR -> standard MIDI file via mido.

Phase 1 emits MIDI only. Phase 2 will add MusicXML (music21) and audio
rendering (FluidSynth -> WAV -> MP3 via ffmpeg).
"""

from __future__ import annotations

import mido

TICKS_PER_BEAT = 480

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
    programs = GM_PROGRAMS.get(genre, GM_PROGRAMS["ambient"])
    pedals = ir.get("pedals", [])

    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)

    # tempo + meter on track 0
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo",
                                 tempo=mido.bpm2tempo(bpm), time=0))
    n, d = (int(x) for x in spec["meter"].split("/"))
    meta.append(mido.MetaMessage("time_signature",
                                 numerator=n, denominator=d, time=0))
    meta.append(mido.MetaMessage("track_name",
                                 name=f"busy day {ir['meta']['date']}", time=0))
    mid.tracks.append(meta)

    # melody (with sustain pedal CC64 on the same channel)
    mel = _track_with_program("melody", programs["melody"], channel=0)
    mel_msgs = _events_to_messages(ir["tracks"]["melody"], channel=0, bpb=bpb)
    mel_msgs += _pedal_messages(pedals, channel=0, bpb=bpb)
    _flush_track(mel, mel_msgs)
    mid.tracks.append(mel)

    # harmony (also pedaled to keep pad legato across chord changes)
    har = _track_with_program("harmony", programs["harmony"], channel=1)
    har_msgs = _events_to_messages(ir["tracks"]["harmony"], channel=1, bpb=bpb)
    har_msgs += _pedal_messages(pedals, channel=1, bpb=bpb)
    _flush_track(har, har_msgs)
    mid.tracks.append(har)

    # bass (no pedal — would muddy the low register)
    bas = _track_with_program("bass", programs["bass"], channel=2)
    _flush_track(bas,
                 _events_to_messages(ir["tracks"]["bass"], channel=2, bpb=bpb))
    mid.tracks.append(bas)

    mid.save(path)
