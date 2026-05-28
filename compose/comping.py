"""Genre-aware harmony comping + bass walking patterns.

Each *pattern* is a list of (start_beat, dur, voice_kind, vel_mult)
tuples and runs inside one bar. To break the "same rhythm 16 bars in a
row" feel, every (genre, meter) holds 1-2 patterns: a canonical cell
and an alt cell. The arranger calls `harmony_pattern_for(genre, meter,
section, rng)` once per bar and the picker biases:

    INTRO / OUTRO    → canonical (calm bookends)
    A                → 70% canonical / 30% alt
    B                → 25% canonical / 75% alt   (audibly different)
    A_PRIME          → 60% canonical / 40% alt   (back, but not identical)

Bass uses the same scheme via `bass_pattern_for`. Single-cell entries
just always return that cell. The percussion patterns below stay
single-cell on purpose — the pulse layer should be steady so the
listener can feel time even while the chord rhythm shifts.

Voice kinds (for harmony):
  "all"      — full chord (root + 3rd + 5th [+ 7th if seventh voicing])
  "top"      — 3rd + 5th [+ 7th]   (no root)
  "top3"     — top three voices
  "root"     — root only
  "fifth"    — 5th only
  "root_5"   — root + 5th

Voice kinds (for bass):
  "root"     — chord root, low octave
  "fifth"    — chord 5th, low octave
  "third"    — chord 3rd, low octave
  "fifth_up" — 5th one octave above bass register (alberti pattern)
"""

from __future__ import annotations

from random import Random


# ── harmony per (genre, beats_per_bar) ─────────────────────────────
# value = list of patterns (canonical first, alt second)

_H44 = {
    "ambient": [
        # canonical: pure pad, whole note — the genre's anchor
        [(0.0, 4.0, "all",   1.00)],
        # alt 1: split mid-bar into two halves so the pad "breathes"
        [(0.0, 2.0, "all",   1.00),
         (2.0, 2.0, "top",   0.85)],
        # alt 2: delayed swell — silence on beat 1, pad enters on the
        # "and of 1" and holds. Eno-style suspension where the bar
        # appears to start late. Stays minimal (1 hit only).
        [(0.5, 3.5, "all",   0.95)],
    ],
    "neo_classical": [
        # canonical: block + 3 stabs (Yiruma-style)
        [(0.0, 1.0, "all",   1.00),
         (1.0, 1.0, "top",   0.85),
         (2.0, 1.0, "top",   0.85),
         (3.0, 1.0, "top",   0.80)],
        # alt 1: longer downbeat + arpeggio tail
        [(0.0, 2.0, "all",   1.00),
         (2.0, 0.5, "top",   0.80),
         (2.5, 0.5, "fifth", 0.78),
         (3.0, 0.5, "top",   0.85),
         (3.5, 0.5, "root_5", 0.85)],
        # alt 2: rolled arpeggio — broken chord climbing through eighths
        # (Einaudi/Tiersen sustain-pedal feel, sounds like a single
        # rolled chord with the pedal down).
        [(0.0, 0.5, "root",   0.90),
         (0.5, 0.5, "fifth",  0.85),
         (1.0, 0.5, "top",    0.85),
         (1.5, 2.5, "top3",   0.92)],
        # alt 3: held suspension + answer — 3-beat sustain releases into
        # a quiet quarter-note answer. Voice leading shows in the answer.
        [(0.0, 3.0, "all",    1.00),
         (3.0, 1.0, "top",    0.78)],
    ],
    "folk": [
        # canonical: alternating root_5 / top quarters (boom-chuck)
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 1.0, "top",    0.90),
         (2.0, 1.0, "root_5", 0.90),
         (3.0, 1.0, "top",    0.88)],
        # alt 1: same shell, eighth-note answer on beats 2 & 4
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 0.5, "top",    0.88),
         (1.5, 0.5, "top",    0.82),
         (2.0, 1.0, "root_5", 0.92),
         (3.0, 0.5, "top",    0.88),
         (3.5, 0.5, "top",    0.82)],
        # alt 2: Celtic drone — open root_5 held for 2 beats then a
        # single chord answer on 3. Pairs perfectly with the open_fifth
        # voicing the arranger leans into for folk (Muji-Celtic core).
        [(0.0, 2.0, "root_5", 0.95),
         (2.0, 2.0, "top",    0.85)],
        # alt 3: lilting pickup — silence on beat 1, eighth pickup on
        # the "and of 1" into a held chord. The "anacrusis" pulls the
        # listener forward (jig feel even in 4/4).
        [(0.5, 0.5, "root_5", 0.85),
         (1.0, 1.5, "top",    0.92),
         (2.5, 1.5, "root_5", 0.88)],
    ],
    "bossa_nova": [
        # canonical: classic bossa básica — root on 1, anticipated chord
        # on the "and of 1", fifth on 3, two-note tail
        [(0.0,  0.5, "root",   0.95),
         (0.75, 1.0, "top",    0.92),
         (2.0,  0.5, "fifth",  0.85),
         (2.5,  0.5, "top",    0.92),
         (3.0,  1.0, "top",    0.90)],
        # alt 1: same shape, second-half pushed back ("late comp")
        [(0.0,  0.75, "root",  0.95),
         (0.75, 1.25, "top",   0.92),
         (2.5,  0.5, "fifth",  0.88),
         (3.0,  0.5, "top",    0.90),
         (3.5,  0.5, "top",    0.85)],
        # alt 2: partido-alto "esparso" — only 2 hits, heavy syncopation,
        # creates breathing room. Very different rhythmic shape from the
        # other cells — listener immediately hears the change.
        [(0.0,  1.5, "all",    0.95),
         (2.5,  1.5, "top",    0.88)],
        # alt 3: "ballad bossa" — Tom Jobim style. Long sustained
        # downbeat chord, ghost chord on the "and of 1", anticipated
        # pickup on 4.5. Sparser and more contemplative than alt 2,
        # asymmetric so it contrasts the "esparso" two-equal-halves shape.
        # Replaces the previous "samba dense" cell which leaned too
        # samba-batida and broke the bossa identity ("soft and airy").
        [(0.0, 1.5, "all",    0.92),
         (1.5, 0.5, "top",    0.78),
         (3.5, 0.5, "top",    0.82)],
    ],
    "jazz_ballad": [
        # canonical: long stabs
        [(0.0, 2.0, "top3",   0.90),
         (2.0, 0.5, "top",    0.80),
         (2.5, 1.5, "top3",   0.88)],
        # alt 1: 4 stabs, busier
        [(0.0, 1.0, "top3",   0.90),
         (1.5, 0.5, "top",    0.80),
         (2.0, 1.0, "top3",   0.85),
         (3.5, 0.5, "top",    0.82)],
        # alt 2: rubato whole — single sustained chord across the bar.
        # The "Bill Evans pause" — gives the melody/walking bass full
        # spotlight. Most contrasting cell against the busy alt 1.
        [(0.0, 4.0, "top3",   0.88)],
        # alt 3: two-stab breath — chord on 1 and chord on 3 only,
        # very spacious. Classic ballad piano comping where the left
        # hand sits out the off-beats.
        [(0.0, 2.0, "top3",   0.90),
         (2.0, 2.0, "top3",   0.85)],
    ],
    "lo_fi": [
        # canonical: lazy 2-hit (off-beat 1 and off-beat 3)
        [(0.5, 1.5, "top",    0.85),
         (2.5, 1.5, "top",    0.82)],
        # alt 1: 3 hits with anticipation
        [(0.5, 1.0, "top",    0.85),
         (1.75, 0.75, "top",  0.80),
         (2.5, 1.5, "top",    0.82)],
        # alt 2: off-beat float — chords on the "and of 2" and
        # "and of 4" only. Pulls the chord off the strong beats
        # entirely, very lazy/floating.
        [(1.5, 1.0, "top",    0.82),
         (3.5, 0.5, "top",    0.78)],
        # alt 3: long sustain — single chord held the entire bar.
        # The "tape hiss" cell where the chord just hangs in the air.
        [(0.0, 4.0, "top",    0.85)],
    ],
}

_H34 = {
    "ambient": [
        [(0.0, 3.0, "all", 1.00)],
        [(0.0, 1.5, "all", 1.00),
         (1.5, 1.5, "top", 0.85)],
    ],
    "neo_classical": [
        [(0.0, 1.0, "all", 1.00),
         (1.0, 1.0, "top", 0.85),
         (2.0, 1.0, "top", 0.80)],
        [(0.0, 1.5, "all", 1.00),
         (1.5, 0.5, "top", 0.85),
         (2.0, 0.5, "fifth", 0.80),
         (2.5, 0.5, "top",  0.85)],
    ],
    "folk": [
        # canonical: waltz strum
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 1.0, "top",    0.88),
         (2.0, 1.0, "top",    0.85)],
        # alt 1: eighth answer on beat 2
        [(0.0, 1.0, "root_5", 0.95),
         (1.0, 0.5, "top",    0.88),
         (1.5, 0.5, "top",    0.82),
         (2.0, 1.0, "top",    0.85)],
        # alt 2: Celtic waltz drone — open root_5 held 2 beats then a
        # single chord on 3. The "Loreena McKennitt" waltz feel.
        [(0.0, 2.0, "root_5", 0.95),
         (2.0, 1.0, "top",    0.88)],
    ],
    "bossa_nova": [
        # canonical: bossa waltz (rare but valid — "Waltz for Debby"
        # vibe when bossa hits 3/4)
        [(0.0, 1.0, "root",   0.95),
         (1.0, 1.0, "top",    0.90),
         (2.0, 1.0, "top",    0.88)],
        # alt 1: anticipated answer
        [(0.0, 0.5, "root",   0.95),
         (0.75, 1.25, "top",  0.90),
         (2.0, 1.0, "top",    0.88)],
        # alt 2: sparse — chord on 1 + anticipated pickup on 2.5
        [(0.0, 1.5, "all",    0.92),
         (2.5, 0.5, "top",    0.82)],
    ],
    "jazz_ballad": [
        [(0.0, 3.0, "top3", 0.90)],
        [(0.0, 1.5, "top3", 0.90),
         (1.5, 1.5, "top",  0.85)],
    ],
    "lo_fi": [
        [(0.5, 1.0, "top", 0.85),
         (2.0, 1.0, "top", 0.80)],
        [(0.0, 1.0, "top", 0.85),
         (1.5, 1.5, "top", 0.82)],
    ],
}

_H68 = {
    "ambient": [
        [(0.0, 6.0, "all", 1.00)],
        [(0.0, 3.0, "all", 1.00),
         (3.0, 3.0, "top", 0.85)],
    ],
    "neo_classical": [
        [(0.0, 1.5, "all", 1.00),
         (1.5, 1.5, "top", 0.85),
         (3.0, 1.5, "top", 0.85),
         (4.5, 1.5, "top", 0.80)],
        [(0.0, 3.0, "all", 1.00),
         (3.0, 1.0, "top",   0.85),
         (4.0, 1.0, "fifth", 0.80),
         (5.0, 1.0, "top",   0.85)],
    ],
    "folk": [
        # canonical: jig pulse — 6/8 in two dotted-quarter halves
        [(0.0, 1.5, "root_5", 0.95),
         (1.5, 1.5, "top",    0.88),
         (3.0, 1.5, "root_5", 0.92),
         (4.5, 1.5, "top",    0.85)],
        # alt 1: subdivided eighths in beat 2 (Celtic ornament feel)
        [(0.0, 1.5, "root_5", 0.95),
         (1.5, 0.75, "top",   0.88),
         (2.25, 0.75, "top",  0.80),
         (3.0, 1.5, "root_5", 0.92),
         (4.5, 1.5, "top",    0.85)],
        # alt 2: drone jig — open fifth held for the full first half,
        # accent chord on beats 4 and 5.5. The "Riverdance drone"
        # where the bagpipe-like chord sustains underneath.
        [(0.0, 3.0, "root_5", 0.95),
         (3.0, 1.5, "top",    0.85),
         (4.5, 1.5, "top",    0.82)],
        # alt 3: pickup-and-fall — eighth pickup on the "and of 6"
        # (last eighth of the previous bar, here as bar start), held
        # chord through beats 1-3, single chord on beat 4. Lilting.
        [(0.0, 0.5, "root_5", 0.85),
         (0.5, 2.5, "top",    0.92),
         (3.0, 1.5, "root_5", 0.90),
         (4.5, 1.5, "top",    0.85)],
    ],
    "bossa_nova": [
        [(0.0, 1.5, "root",  0.95),
         (1.5, 1.5, "top",   0.90),
         (3.0, 1.5, "fifth", 0.85),
         (4.5, 1.5, "top",   0.90)],
        [(0.0, 0.75, "root", 0.95),
         (0.75, 2.25, "top", 0.90),
         (3.0, 0.75, "fifth", 0.85),
         (3.75, 2.25, "top", 0.88)],
    ],
    "jazz_ballad": [
        [(0.0, 3.0, "top3", 0.90),
         (3.0, 3.0, "top3", 0.88)],
        [(0.0, 1.5, "top3", 0.90),
         (1.5, 1.5, "top",  0.82),
         (3.0, 3.0, "top3", 0.88)],
    ],
    "lo_fi": [
        [(1.5, 1.5, "top", 0.85),
         (4.5, 1.5, "top", 0.80)],
        [(0.0, 1.0, "top", 0.85),
         (3.0, 1.5, "top", 0.82)],
    ],
}

# ── bass per (genre, beats_per_bar) ────────────────────────────────
_B44 = {
    "ambient": [
        # canonical: pure root drone for the whole bar
        [(0.0, 4.0, "root")],
        # alt 1: half + half root/fifth (subtle harmonic motion)
        [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],
        # alt 2: half-bar bass — root for 2 beats, then silence. Lets
        # the drone (when present) or the harmony pad carry beats 3-4
        # alone. Maximum sparseness without going entirely empty.
        [(0.0, 2.0, "root")],
        # alt 3: gentle quarter pulse with chord-tone arch. Adds a
        # baseline pulse so ambient at faster tempos doesn't feel
        # draggy. Root anchors beats 1+3, third and fifth fill 2+4
        # for smooth motion (still ambient-quiet via velocity curve).
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
    ],
    "neo_classical": [
        # canonical: alberti — 8 eighth-note arpeggios (Mozart left hand)
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth_up"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth_up"),
         (2.0, 0.5, "root"),
         (2.5, 0.5, "fifth_up"),
         (3.0, 0.5, "third"),
         (3.5, 0.5, "fifth_up")],
        # alt 1: walking quarters
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
        # alt 2: pedal point — held root for the whole bar. The classic
        # "organ pedal" where the bass anchors while the harmony moves
        # above. Pairs with the held-suspension harmony cell.
        [(0.0, 4.0, "root")],
        # alt 3: octave-leap — root low, then root mid-high in the
        # second half (figured-bass tradition; gives a sense of
        # vertical lift mid-bar without changing chord function).
        [(0.0, 2.0, "root"),
         (2.0, 2.0, "fifth_up")],
        # alt 4: scalar walking — eighth-note bass through octave-
        # displaced chord tones for melodic shape (Schubert-lieder
        # bass tradition). Different from alberti: alberti hammers
        # the low chord-tone + fifth_up alternation; this one walks.
        [(0.0, 0.5, "fifth_up"),
         (0.5, 0.5, "third"),
         (1.0, 0.5, "root"),
         (1.5, 0.5, "fifth"),
         (2.0, 0.5, "third"),
         (2.5, 0.5, "fifth_up"),
         (3.0, 0.5, "fifth"),
         (3.5, 0.5, "root")],
    ],
    "folk": [
        # canonical: boom-chick (root on 1+3, fifth on 2+4)
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "root"),
         (3.0, 1.0, "fifth")],
        # alt 1: walking 1-5-3-↑5 (third + upper fifth = scale movement)
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "third"),
         (3.0, 1.0, "fifth_up")],
        # alt 2: Celtic drone root — root held all 4 beats. Pairs with
        # the open_fifth harmony voicing for the "ancient modal" sound.
        # The bass drones, the harmony breathes. Pure Muji-Celtic core.
        [(0.0, 4.0, "root")],
        # alt 3: stepwise scale walk — 1-2-3-5 (passing tone on beat 2).
        # Half-step movement gives a more "ballad-folk" feel than the
        # canonical boom-chick. Sounds like a Nick Drake bass line.
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "root")],
        # alt 4: galloping 8th-note pulse. Root anchors every strong
        # beat; off-beats walk through chord tones for melodic shape.
        # Doubles the bass density of canonical so faster tempos
        # actually feel propulsive. Tom Petty / Americana feel.
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth"),
         (1.0, 0.5, "root"),
         (1.5, 0.5, "third"),
         (2.0, 0.5, "root"),
         (2.5, 0.5, "fifth"),
         (3.0, 0.5, "fifth"),
         (3.5, 0.5, "fifth_up")],
    ],
    "bossa_nova": [
        # canonical: classic bossa "1.5 + 0.5 + 1.5 + 0.5" rhythm —
        # dotted-quarter on 1, eighth pickup on 2.5 to dotted-quarter
        # on 3, eighth pickup on 4.5 back to root.
        [(0.0, 1.5, "root"),
         (1.5, 0.5, "fifth"),
         (2.0, 1.5, "fifth"),
         (3.5, 0.5, "root")],
        # alt 1: same rhythm, walking pitches (1-3-5-↑5)
        [(0.0, 1.5, "root"),
         (1.5, 0.5, "third"),
         (2.0, 1.5, "fifth"),
         (3.5, 0.5, "fifth_up")],
        # alt 2: tumbao-feel — long root, syncopated fifth that
        # anticipates beat 3, eighth pickup. The half-bar lopsided shape
        # contrasts the symmetric canonical 1.5+0.5+1.5+0.5.
        [(0.0, 2.5, "root"),
         (2.5, 1.0, "fifth"),
         (3.5, 0.5, "root")],
        # alt 3: "2-feel" — half-note root + half-note fifth. Very sparse,
        # ballad-bossa. Pulls the energy back so the melody stands out.
        [(0.0, 2.0, "root"),
         (2.0, 2.0, "fifth")],
        # alt 4: chord-tone walking quarters. Same hit count as canonical
        # but breaks the symmetric 1.5+0.5+1.5+0.5 rhythm and moves
        # melodically through root/third/fifth. Bossa-jazz hybrid; the
        # Jobim recordings where the bass takes a melodic role.
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
    ],
    "jazz_ballad": [
        # canonical: walking quarters 1-3-5-3
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
        # alt 1: chromatic-feeling fifth_up between
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth_up"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
        # alt 2: pedal-then-walk — root for 2 beats, walk in beats 3-4.
        # Gives the bar a "two-feel" first half and "four-feel" second
        # half; classic Bill Evans trio bass move.
        [(0.0, 2.0, "root"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
        # alt 3: half-note bass — root + fifth, two hits only. Pairs
        # with the "ballad rubato" whole-note harmony cell to create a
        # truly spacious bar.
        [(0.0, 2.0, "root"),
         (2.0, 2.0, "fifth")],
        # alt 4: bebop straight-eighth walking. 8 hits per bar through
        # all chord tones with octave displacement. The "Paul Chambers"
        # / "Ray Brown" walking bass at double density.
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "third"),
         (1.0, 0.5, "fifth"),
         (1.5, 0.5, "fifth_up"),
         (2.0, 0.5, "fifth"),
         (2.5, 0.5, "third"),
         (3.0, 0.5, "fifth"),
         (3.5, 0.5, "fifth_up")],
    ],
    "lo_fi": [
        # canonical: half + half root/fifth
        [(0.0, 2.0, "root"),
         (2.0, 2.0, "fifth")],
        # alt 1: 1-3-5-3 walking quarters
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth"),
         (3.0, 1.0, "third")],
        # alt 2: 808-style sustain — long root with a brief fifth
        # ghost on 3.5 (anticipates beat 4). The fifth is short like
        # a sub-bass tail. Boom-bap sub-bass aesthetic.
        [(0.0, 3.5, "root"),
         (3.5, 0.5, "fifth")],
        # alt 3: anticipated drop — root on 1, fifth pushed to 3.5
        # (pulls the bar forward). Lazy and slightly off-grid.
        [(0.0, 3.5, "root"),
         (3.5, 0.5, "fifth_up")],
        # alt 4: active boom-bap — 6 hits with root anchors on strong
        # beats and syncopated fifth on the ands. Adds pulse so lo_fi
        # at slower tempos doesn't feel draggy. J Dilla micro-syncopation.
        [(0.0, 0.5, "root"),
         (1.5, 0.5, "fifth"),
         (2.0, 0.5, "root"),
         (2.5, 0.5, "fifth_up"),
         (3.0, 0.5, "root"),
         (3.5, 0.5, "fifth")],
    ],
}

_B34 = {
    "ambient": [
        [(0.0, 3.0, "root")],
        [(0.0, 1.5, "root"), (1.5, 1.5, "fifth")],
    ],
    "neo_classical": [
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth_up"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth_up"),
         (2.0, 0.5, "root"),
         (2.5, 0.5, "fifth_up")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth")],
    ],
    "folk": [
        # canonical: waltz boom-chick-chick (root + 2 fifths)
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "fifth")],
        # alt 1: walking 1-3-5
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth")],
        # alt 2: Celtic drone — root held for the full bar
        [(0.0, 3.0, "root")],
        # alt 3: 8th-note waltz pulse — 6 hits with chord-tone motion.
        # Drives slow 3/4 tempos so the waltz doesn't drag.
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth"),
         (2.0, 0.5, "fifth"),
         (2.5, 0.5, "third")],
    ],
    "bossa_nova": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "root")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth")],
    ],
    "jazz_ballad": [
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "third"),
         (2.0, 1.0, "fifth")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "third")],
    ],
    "lo_fi": [
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth")],
        [(0.0, 1.0, "root"),
         (1.0, 1.0, "fifth"),
         (2.0, 1.0, "root")],
    ],
}

_B68 = {
    "ambient": [
        [(0.0, 6.0, "root")],
        [(0.0, 3.0, "root"), (3.0, 3.0, "fifth")],
    ],
    "neo_classical": [
        [(0.0, 0.5, "root"),
         (0.5, 0.5, "fifth_up"),
         (1.0, 0.5, "third"),
         (1.5, 0.5, "fifth_up"),
         (3.0, 0.5, "fifth"),
         (3.5, 0.5, "fifth_up"),
         (4.0, 0.5, "third"),
         (4.5, 0.5, "fifth_up")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "third"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "third")],
    ],
    "folk": [
        # canonical: jig boom-chick (root + fifth alternating dotted-quarters)
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 1.5, "fifth")],
        # alt 1: substitute third on the last quarter (motion)
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 1.5, "third")],
        # alt 2: drone root — held for the full bar (Celtic bagpipe drone)
        [(0.0, 6.0, "root")],
        # alt 3: rocking root-fifth — root for the first half-bar,
        # fifth for the second. Slower harmonic rhythm than canonical.
        [(0.0, 3.0, "root"),
         (3.0, 3.0, "fifth")],
        # alt 4: tight jig gallop — root anchors on the two main beats
        # (1 and 4) with eighth-note chord-tone fills between. The
        # propulsive Celtic dance bass that drives even slow jigs.
        [(0.0, 1.5, "root"),
         (1.5, 0.5, "fifth"),
         (2.0, 0.5, "third"),
         (2.5, 0.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 0.5, "fifth"),
         (5.0, 0.5, "third"),
         (5.5, 0.5, "fifth")],
    ],
    "bossa_nova": [
        [(0.0, 1.5, "root"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "root")],
        [(0.0, 3.0, "root"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "fifth")],
    ],
    "jazz_ballad": [
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "third"),
         (3.0, 1.5, "fifth"),
         (4.5, 1.5, "third")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "third"),
         (4.5, 1.5, "fifth")],
    ],
    "lo_fi": [
        [(0.0, 3.0, "root"),
         (3.0, 3.0, "fifth")],
        [(0.0, 1.5, "root"),
         (1.5, 1.5, "fifth"),
         (3.0, 1.5, "root"),
         (4.5, 1.5, "fifth")],
    ],
}


def _table(beats_per_bar: int):
    if beats_per_bar == 3:
        return _H34, _B34
    if beats_per_bar == 6:
        return _H68, _B68
    return _H44, _B44


# ── section-aware probability of choosing the alt cell ────────────
_ALT_BIAS = {
    "INTRO":   0.00,
    "A":       0.30,
    "B":       0.75,
    "A_PRIME": 0.40,
    "OUTRO":   0.00,
}


def _pick_cell(cells, section, rng: Random):
    """Pick canonical or alt cell based on section bias.

    Supports N cells: cells[0] is canonical (the stable default), and
    cells[1:] are alternates. When the alt branch fires, one of the
    alternates is chosen uniformly. Backwards compatible with the
    original 2-cell layout (alt-prob applied to cells[1])."""
    if not cells:
        return []
    if len(cells) == 1:
        return cells[0]
    p_alt = _ALT_BIAS.get(section, 0.30)
    if rng.random() >= p_alt:
        return cells[0]
    if len(cells) == 2:
        return cells[1]
    return rng.choice(cells[1:])


def _maybe_drop_last(events, rng: Random, p: float = 0.12):
    """Tiny breath: occasionally drop the trailing event of a 3+ event
    pattern so the bar feels more spoken than typed."""
    if len(events) >= 3 and rng.random() < p:
        return events[:-1]
    return events


def harmony_pattern_for(genre: str, meter: str,
                        section: str, rng: Random,
                        sub_style: str | None = None):
    bpb = int(meter.split("/")[0])
    cells = _resolve_cells("harmony", genre, sub_style, bpb)
    return _maybe_drop_last(_pick_cell(cells, section, rng), rng)


def bass_pattern_for(genre: str, meter: str,
                     section: str, rng: Random,
                     sub_style: str | None = None):
    bpb = int(meter.split("/")[0])
    cells = _resolve_cells("bass", genre, sub_style, bpb)
    return _maybe_drop_last(_pick_cell(cells, section, rng), rng, p=0.08)


def _resolve_cells(layer: str, genre: str, sub_style: str | None,
                   bpb: int) -> list:
    """Return the cell list for (layer, genre, sub_style, bpb).

    Looks up sub-style-specific pack first (4/4 only — sub-styles aren't
    defined for 3/4 / 6/8 yet). Falls back to the genre-only table when
    sub_style is None or no pack exists for this combo.
    """
    if sub_style and bpb == 4:
        sub_table = _SUB_PACKS.get(layer)
        if sub_table is not None:
            pack = sub_table.get((genre, sub_style))
            if pack:
                return pack
    h, b = _table(bpb)
    if layer == "harmony":
        return h.get(genre, h["ambient"])
    if layer == "bass":
        return b.get(genre, b["ambient"])
    raise ValueError(layer)


# Backward-compat: callers without rng/section get the canonical cell.
def harmony_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    h, _ = _table(bpb)
    cells = h.get(genre, h["ambient"])
    return cells[0] if cells else []


def bass_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    _, b = _table(bpb)
    cells = b.get(genre, b["ambient"])
    return cells[0] if cells else []


# ── voice subset helpers ───────────────────────────────────────────
def chord_subset(chord_pitches, kind: str):
    if not chord_pitches:
        return []
    cp = list(chord_pitches)
    if kind == "all":
        return cp
    if kind == "top":
        return cp[1:]
    if kind == "top3":
        return cp[1:4] if len(cp) > 1 else cp
    if kind == "root":
        return [cp[0]]
    if kind == "fifth":
        return [cp[2]] if len(cp) > 2 else [cp[0]]
    if kind == "root_5":
        return [cp[0], cp[2]] if len(cp) > 2 else [cp[0]]
    return cp


# ── bass pitch resolution ──────────────────────────────────────────
def bass_pitch(degree_to_midi_fn, key, mode, chord_root, kind: str) -> int:
    if kind == "root":
        return degree_to_midi_fn(key, mode, chord_root,
                                 octave_shift=-1, base_octave=2)
    if kind == "fifth":
        return degree_to_midi_fn(key, mode, chord_root + 4,
                                 octave_shift=-1, base_octave=2)
    if kind == "third":
        return degree_to_midi_fn(key, mode, chord_root + 2,
                                 octave_shift=-1, base_octave=2)
    if kind == "fifth_up":
        return degree_to_midi_fn(key, mode, chord_root + 4,
                                 octave_shift=0,  base_octave=3)
    return degree_to_midi_fn(key, mode, chord_root,
                             octave_shift=-1, base_octave=2)


# ── percussion patterns ────────────────────────────────────────────
# Same canonical/alt list-of-cells shape as harmony/bass so the picker
# logic can mirror them. Alt cells are deliberately close to canonical
# (one or two voice swaps, not a different beat) so the pulse stays
# steady while the texture varies.

_P44 = {
    "ambient": [
        # canonical: silent — pad-only texture, no pulse
        [],
        # alt 1: ultra-minimal "clock tick" on beat 1 only. Stays
        # almost subliminal (vel 0.20) so the pad still dominates,
        # but the listener gets a faint pulse signal so the song
        # doesn't feel totally adrift.
        [(0.0, "brush", 0.22)],
        # alt 2: half-bar breath — soft brush on 1 and 3
        [(0.0, "brush", 0.22), (2.0, "brush", 0.18)],
    ],
    "neo_classical": [
        # canonical: light tap on 1 + 3 (Yiruma piano pulse)
        [(0.0, "tap", 0.55), (2.0, "tap", 0.45)],
        # alt 1: tap + brush ghost on the off-beat between
        [(0.0, "tap", 0.55), (1.5, "brush", 0.40), (2.0, "tap", 0.45)],
        # alt 2: pedal-like single tap on 1 (very sparse). Pairs
        # with the held-suspension harmony cell where the bar is
        # essentially one sustained chord.
        [(0.0, "tap", 0.50)],
        # alt 3: light march — tap every quarter (alternating
        # strong/weak). Used sparingly so it doesn't feel mechanical.
        [(0.0, "tap", 0.55), (1.0, "tap", 0.32),
         (2.0, "tap", 0.50), (3.0, "tap", 0.32)],
    ],
    "folk": [
        # canonical: boom-tap on 1+3, brush back-beat on 2+4
        [(0.0, "tap", 0.50), (1.0, "brush", 0.65),
         (2.0, "tap", 0.45), (3.0, "brush", 0.65)],
        # alt 1: double-brush on 2 & 4 for emphasis
        [(0.0, "tap", 0.50),
         (1.0, "brush", 0.65), (1.5, "brush", 0.45),
         (2.0, "tap", 0.45),
         (3.0, "brush", 0.65), (3.5, "brush", 0.45)],
        # alt 2: all-quarter brush (lighter, evenly spaced pulse).
        # Pairs with the Celtic-drone harmony cell where the chord
        # sustains and rhythm becomes the lead voice.
        [(0.0, "brush", 0.55), (1.0, "brush", 0.50),
         (2.0, "brush", 0.55), (3.0, "brush", 0.50)],
        # alt 3: folk-stomp — kick on 1+3, snare on 2+4
        # (Mumford & Sons / Avett Brothers feel). Different timbre
        # from the boom-tap canonical for clear contrast.
        [(0.0, "kick", 0.65), (1.0, "snare", 0.55),
         (2.0, "kick", 0.62), (3.0, "snare", 0.55)],
    ],
    "bossa_nova": [
        # canonical: full shaker 8ths — the bossa pulse signature
        [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
         (1.0, "shaker", 0.55), (1.5, "shaker", 0.40),
         (2.0, "shaker", 0.55), (2.5, "shaker", 0.40),
         (3.0, "shaker", 0.55), (3.5, "shaker", 0.40)],
        # alt 1: tap accent on 1 + 3 + shaker between (Astrud Gilberto)
        [(0.0, "tap",    0.55),
         (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
         (1.5, "shaker", 0.35),
         (2.0, "tap",    0.50),
         (2.5, "shaker", 0.35), (3.0, "shaker", 0.45),
         (3.5, "shaker", 0.35)],
        # alt 2: shaker on off-beats only — lazy, half-density.
        # Sounds like the player is brushing every other 8th.
        [(0.5, "shaker", 0.48), (1.5, "shaker", 0.42),
         (2.5, "shaker", 0.48), (3.5, "shaker", 0.42)],
        # alt 3: ballad bossa — shaker on 1+3, brush back-beat-ish on
        # 1.5. Very spacious (Tom Jobim solo recordings).
        [(0.0, "shaker", 0.40), (1.5, "brush", 0.38),
         (3.0, "shaker", 0.40)],
    ],
    "jazz_ballad": [
        # canonical: ride with brush back-beats — quintessential
        # jazz comping
        [(0.0, "ride", 0.40), (1.0, "brush", 0.55),
         (1.5, "ride", 0.30), (2.0, "ride", 0.40),
         (2.5, "ride", 0.30), (3.0, "brush", 0.55),
         (3.5, "ride", 0.30)],
        # alt 1: brushes only — softer chorus-like feel
        [(0.0, "brush", 0.45), (1.0, "brush", 0.55),
         (2.0, "brush", 0.45), (3.0, "brush", 0.55)],
        # alt 2: ride on 2 & 4 only — extremely spacious "tea-room"
        # cell where the bass walks alone for most of the bar
        [(1.0, "ride", 0.42), (3.0, "ride", 0.42)],
        # alt 3: brush back-beat — chunky snare-like on 2 + 4 (jazz
        # waltz / shuffle hybrid feel). Pairs with the rubato whole-
        # note harmony cell.
        [(1.0, "brush", 0.55), (3.0, "brush", 0.55)],
    ],
    "lo_fi": [
        # canonical: kick + 8th-note hats + snare on 3
        [(0.0, "kick",  0.75),
         (0.5, "hat",   0.30), (1.0, "hat", 0.30), (1.5, "hat", 0.30),
         (2.0, "snare", 0.65),
         (2.5, "hat",   0.30), (3.0, "hat", 0.30), (3.5, "hat", 0.30)],
        # alt 1: kick on 1+2.5 (syncopated), snare 3
        [(0.0, "kick",  0.75),
         (0.5, "hat",   0.30), (1.0, "hat", 0.30), (1.5, "hat", 0.30),
         (2.0, "snare", 0.60),
         (2.5, "kick",  0.55), (3.0, "hat", 0.30), (3.5, "hat", 0.30)],
        # alt 2: half-time — kick on 1, snare on 3 only. The "boom-bap
        # sub" feel where the kit lays back and the bass+pad carry.
        [(0.0, "kick", 0.72), (2.0, "snare", 0.60)],
        # alt 3: muted kick eighths + hats — kick on every beat at
        # lower vel for a propulsive but soft groove
        [(0.0, "kick", 0.62), (0.5, "hat", 0.30),
         (1.0, "kick", 0.48), (1.5, "hat", 0.30),
         (2.0, "snare", 0.62), (2.5, "hat", 0.30),
         (3.0, "kick", 0.48), (3.5, "hat", 0.30)],
    ],
}

# ── percussion fill cells (transition bars only) ──────────────────
# Used at the last bar of A→B and B→A' transitions to signal the
# section change. Deliberately busier than any normal cell so the
# listener feels the structural shift. Kept in a separate dict so
# the random alt-picker never selects them on a non-transition bar.
_PFILL_44 = {
    "ambient":       [(2.0, "brush", 0.32), (3.0, "brush", 0.28)],
    "neo_classical": [(0.0, "tap", 0.50),
                      (2.0, "tap", 0.50), (2.5, "brush", 0.40),
                      (3.0, "tap", 0.40), (3.5, "brush", 0.40)],
    "folk":          [(0.0, "tap", 0.55), (0.5, "brush", 0.40),
                      (1.0, "brush", 0.55), (1.5, "brush", 0.40),
                      (2.0, "tap", 0.50), (2.5, "brush", 0.45),
                      (3.0, "brush", 0.55), (3.5, "brush", 0.45)],
    # bossa: clave-like fill (3-2 son pattern) instead of plain shaker
    "bossa_nova":    [(0.0, "tap", 0.70), (1.5, "tap", 0.50),
                      (2.5, "tap", 0.65), (3.0, "tap", 0.50),
                      (0.0, "shaker", 0.45), (0.5, "shaker", 0.35),
                      (1.0, "shaker", 0.45), (1.5, "shaker", 0.35),
                      (2.0, "shaker", 0.45), (2.5, "shaker", 0.35),
                      (3.0, "shaker", 0.45), (3.5, "shaker", 0.35)],
    "jazz_ballad":   [(0.0, "ride", 0.45), (0.5, "ride", 0.32),
                      (1.0, "brush", 0.58), (1.5, "ride", 0.32),
                      (2.0, "ride", 0.45), (2.5, "ride", 0.32),
                      (3.0, "brush", 0.58), (3.5, "ride", 0.32)],
    # lo_fi: trap-style hi-hat roll
    "lo_fi":         [(0.0, "kick", 0.75), (0.0, "hat", 0.35),
                      (0.5, "hat", 0.35), (1.0, "hat", 0.30),
                      (1.5, "hat", 0.35),
                      (2.0, "snare", 0.62),
                      (2.5, "hat", 0.30), (3.0, "hat", 0.35),
                      (3.5, "hat", 0.35), (3.75, "snare", 0.45)],
}

_P34 = {
    "ambient":      [[], [(0.0, "brush", 0.20)]],
    "neo_classical": [
        [(0.0, "tap", 0.55)],
        [(0.0, "tap", 0.55), (2.0, "tap", 0.40)],
        [(0.0, "tap", 0.50), (1.0, "tap", 0.30), (2.0, "tap", 0.30)],
    ],
    "folk": [
        # canonical: waltz boom-chick-chick
        [(0.0, "tap", 0.55), (1.0, "brush", 0.55), (2.0, "brush", 0.55)],
        # alt 1: brush 8th split on beat 2
        [(0.0, "tap", 0.55), (1.0, "brush", 0.55),
         (1.5, "brush", 0.40), (2.0, "brush", 0.55)],
        # alt 2: all-brush waltz (lighter)
        [(0.0, "brush", 0.50), (1.0, "brush", 0.50), (2.0, "brush", 0.50)],
        # alt 3: stomp waltz — kick on 1, snare on 2 + 3
        [(0.0, "kick", 0.65), (1.0, "snare", 0.50), (2.0, "snare", 0.45)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
         (1.0, "shaker", 0.50), (1.5, "shaker", 0.40),
         (2.0, "shaker", 0.50), (2.5, "shaker", 0.40)],
        [(0.0, "tap",    0.50),
         (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
         (1.5, "shaker", 0.35), (2.0, "shaker", 0.45),
         (2.5, "shaker", 0.35)],
        # alt 2: half-density shaker (off-beats only)
        [(0.5, "shaker", 0.42), (1.5, "shaker", 0.42),
         (2.5, "shaker", 0.42)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (1.0, "brush", 0.55), (2.0, "ride", 0.40)],
        [(0.0, "brush", 0.45), (1.0, "brush", 0.55), (2.0, "brush", 0.45)],
        [(1.0, "ride", 0.42), (2.0, "ride", 0.42)],  # super sparse
    ],
    "lo_fi": [
        [(0.0, "kick", 0.70), (1.0, "snare", 0.55), (2.0, "snare", 0.55)],
        [(0.0, "kick", 0.70), (1.5, "snare", 0.55),
         (2.0, "hat", 0.30), (2.5, "hat", 0.30)],
        # alt 2: half-time waltz
        [(0.0, "kick", 0.72), (2.0, "snare", 0.55)],
    ],
}
_PFILL_34 = {
    "ambient":       [(0.0, "brush", 0.28), (2.0, "brush", 0.22)],
    "neo_classical": [(0.0, "tap", 0.50), (1.0, "brush", 0.40),
                      (2.0, "tap", 0.40), (2.5, "brush", 0.40)],
    "folk":          [(0.0, "tap", 0.55),
                      (1.0, "brush", 0.55), (1.5, "brush", 0.45),
                      (2.0, "brush", 0.55), (2.5, "brush", 0.45)],
    "bossa_nova":    [(0.0, "tap", 0.60), (0.5, "shaker", 0.40),
                      (1.0, "shaker", 0.45), (1.5, "shaker", 0.40),
                      (2.0, "shaker", 0.45), (2.5, "shaker", 0.40)],
    "jazz_ballad":   [(0.0, "ride", 0.45), (1.0, "brush", 0.58),
                      (1.5, "ride", 0.30), (2.0, "ride", 0.45),
                      (2.5, "ride", 0.30)],
    "lo_fi":         [(0.0, "kick", 0.75), (0.5, "hat", 0.35),
                      (1.0, "hat", 0.30), (1.5, "hat", 0.35),
                      (2.0, "snare", 0.60), (2.5, "hat", 0.35)],
}

_P68 = {
    "ambient":      [[], [(0.0, "brush", 0.22), (3.0, "brush", 0.20)]],
    "neo_classical": [
        [(0.0, "tap", 0.55), (3.0, "tap", 0.45)],
        [(0.0, "tap", 0.55), (3.0, "brush", 0.40)],
        [(0.0, "tap", 0.50)],  # sparse
    ],
    "folk": [
        # canonical: dotted-quarter jig pulse
        [(0.0, "tap", 0.55), (3.0, "brush", 0.60)],
        # alt 1: subdivided eighths in beat 2
        [(0.0, "tap", 0.55), (1.5, "brush", 0.40),
         (3.0, "brush", 0.60), (4.5, "brush", 0.40)],
        # alt 2: all-brush jig (lighter)
        [(0.0, "brush", 0.50), (1.5, "brush", 0.40),
         (3.0, "brush", 0.50), (4.5, "brush", 0.40)],
        # alt 3: jig stomp — kick on 1+4, brush off-beats
        [(0.0, "kick", 0.60), (1.5, "brush", 0.40),
         (3.0, "kick", 0.60), (4.5, "brush", 0.40)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (1.0, "shaker", 0.40),
         (2.0, "shaker", 0.40), (3.0, "shaker", 0.55),
         (4.0, "shaker", 0.40), (5.0, "shaker", 0.40)],
        [(0.0, "tap",    0.50),
         (1.0, "shaker", 0.35), (2.0, "shaker", 0.35),
         (3.0, "tap",    0.50),
         (4.0, "shaker", 0.35), (5.0, "shaker", 0.35)],
        # alt 2: shaker on off-beats (3 hits)
        [(1.0, "shaker", 0.45), (2.0, "shaker", 0.40),
         (4.0, "shaker", 0.45), (5.0, "shaker", 0.40)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (3.0, "ride", 0.40),
         (1.5, "brush", 0.45), (4.5, "brush", 0.45)],
        [(0.0, "brush", 0.45), (3.0, "brush", 0.55)],
        [(1.5, "ride", 0.40), (4.5, "ride", 0.40)],  # off-beat ride only
    ],
    "lo_fi": [
        [(0.0, "kick", 0.70), (3.0, "snare", 0.55)],
        [(0.0, "kick", 0.70), (1.5, "hat", 0.30),
         (3.0, "snare", 0.55), (4.5, "hat", 0.30)],
        # alt 2: half-time (one hit only)
        [(0.0, "kick", 0.72)],
    ],
}
_PFILL_68 = {
    "ambient":       [(0.0, "brush", 0.28), (3.0, "brush", 0.25)],
    "neo_classical": [(0.0, "tap", 0.50), (1.5, "brush", 0.40),
                      (3.0, "tap", 0.45), (4.5, "brush", 0.40)],
    "folk":          [(0.0, "tap", 0.55), (1.5, "brush", 0.40),
                      (2.5, "brush", 0.35),
                      (3.0, "brush", 0.60), (4.5, "brush", 0.45),
                      (5.5, "brush", 0.35)],
    "bossa_nova":    [(0.0, "tap", 0.65), (1.0, "shaker", 0.45),
                      (2.0, "shaker", 0.45), (3.0, "tap", 0.55),
                      (4.0, "shaker", 0.45), (5.0, "shaker", 0.45)],
    "jazz_ballad":   [(0.0, "ride", 0.45), (1.5, "brush", 0.55),
                      (3.0, "ride", 0.45), (4.5, "brush", 0.55)],
    "lo_fi":         [(0.0, "kick", 0.75), (1.5, "hat", 0.35),
                      (3.0, "snare", 0.60), (4.5, "hat", 0.35),
                      (5.5, "snare", 0.45)],
}


def percussion_pattern_for(genre: str, meter: str,
                           section: str, rng: Random,
                           sub_style: str | None = None):
    bpb = int(meter.split("/")[0])
    if sub_style and bpb == 4:
        sub_pack = _SUB_PACKS.get("percussion", {}).get((genre, sub_style))
        if sub_pack:
            return _pick_cell(sub_pack, section, rng)
    table = {3: _P34, 4: _P44, 6: _P68}.get(bpb, _P44)
    cells = table.get(genre, [[]])
    return _pick_cell(cells, section, rng)


def percussion_fill_for(genre: str, meter: str):
    """Return the dedicated transition-fill cell for (genre, meter).

    Used at the last bar before a structural section change (A→B,
    B→A'). Busier than any normal cell so the listener feels the
    shift coming. Kept separate from the alt pool so it never fires
    on a non-transition bar."""
    bpb = int(meter.split("/")[0])
    table = {3: _PFILL_34, 4: _PFILL_44, 6: _PFILL_68}.get(bpb, _PFILL_44)
    return table.get(genre, [])


# Backward-compatible: no-rng helper returns the canonical cell.
def percussion_pattern(genre: str, meter: str):
    bpb = int(meter.split("/")[0])
    table = {3: _P34, 4: _P44, 6: _P68}.get(bpb, _P44)
    cells = table.get(genre, [])
    return cells[0] if cells else []


# General MIDI drum notes (channel 9). Used by render.py to give the
# downloaded MIDI a sensible drum kit when opened in a DAW.
GM_DRUM_NOTE = {
    "tap":    75,
    "shaker": 70,
    "brush":  39,
    "ride":   51,
    "kick":   36,
    "snare":  38,
    "hat":    42,
}


# ── sub-style cell packs (4/4 only) ────────────────────────────────
# Each genre's sub-styles override the genre default with a curated
# cell list. "basica/walking/boom_chick" stay close to the genre's
# signature; the alternate sub-style steers the song into a clearly
# different feel (jazz comping, Celtic drone, rubato ballad).

# bossa_nova → básica (classic): keep the dotted-quarter 1.5+0.5 bass
# and anticipated chord — the bossa signature.
_BOSSA_BASICA_H = [
    [(0.0,  0.5, "root",   0.95),
     (0.75, 1.0, "top",    0.92),
     (2.0,  0.5, "fifth",  0.85),
     (2.5,  0.5, "top",    0.92),
     (3.0,  1.0, "top",    0.90)],
    [(0.0,  0.75, "root",  0.95),
     (0.75, 1.25, "top",   0.92),
     (2.5,  0.5, "fifth",  0.88),
     (3.0,  0.5, "top",    0.90),
     (3.5,  0.5, "top",    0.85)],
    # esparso (partido-alto): 2 hits, breathing room
    [(0.0,  1.5, "all",    0.95),
     (2.5,  1.5, "top",    0.88)],
]
_BOSSA_BASICA_B = [
    [(0.0, 1.5, "root"), (1.5, 0.5, "fifth"),
     (2.0, 1.5, "fifth"), (3.5, 0.5, "root")],
    [(0.0, 1.5, "root"), (1.5, 0.5, "third"),
     (2.0, 1.5, "fifth"), (3.5, 0.5, "fifth_up")],
    # tumbao
    [(0.0, 2.5, "root"), (2.5, 1.0, "fifth"), (3.5, 0.5, "root")],
]
_BOSSA_BASICA_P = [
    [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
     (1.0, "shaker", 0.55), (1.5, "shaker", 0.40),
     (2.0, "shaker", 0.55), (2.5, "shaker", 0.40),
     (3.0, "shaker", 0.55), (3.5, "shaker", 0.40)],
    [(0.0, "tap",    0.55),
     (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
     (1.5, "shaker", 0.35),
     (2.0, "tap",    0.50),
     (2.5, "shaker", 0.35), (3.0, "shaker", 0.45),
     (3.5, "shaker", 0.35)],
]

# bossa_nova → jazz (Jobim later years): longer stabs, walking bass,
# brush back-beat. Closer to jazz_ballad than to básica.
_BOSSA_JAZZ_H = [
    # long stab + short reply + long stab (like jazz_ballad canonical)
    [(0.0, 1.5, "all",  0.90),
     (1.5, 0.5, "top",  0.78),
     (2.0, 2.0, "top3", 0.88)],
    # anticipation but with held 7th
    [(0.0,  0.5, "root", 0.92),
     (0.75, 1.25, "top3", 0.90),
     (2.5,  1.5, "top3", 0.85)],
    # full rubato
    [(0.0, 4.0, "top3", 0.88)],
]
_BOSSA_JAZZ_B = [
    # walking quarters 1-3-5-3
    [(0.0, 1.0, "root"), (1.0, 1.0, "third"),
     (2.0, 1.0, "fifth"), (3.0, 1.0, "third")],
    # chromatic feel
    [(0.0, 1.0, "root"), (1.0, 1.0, "third"),
     (2.0, 1.0, "fifth_up"), (3.0, 1.0, "fifth")],
    # half-note (2-feel)
    [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],
]
_BOSSA_JAZZ_P = [
    # brush back-beat (no shaker)
    [(1.0, "brush", 0.55), (3.0, "brush", 0.55)],
    [(0.0, "ride", 0.40), (1.0, "brush", 0.55),
     (2.0, "ride", 0.40), (3.0, "brush", 0.55)],
    # light shaker + brush hybrid (subtle bridge to básica)
    [(0.0, "shaker", 0.35), (1.0, "brush", 0.50),
     (2.0, "shaker", 0.30), (3.0, "brush", 0.50)],
]

# folk → boom_chick (current default): root+fifth alternation, brush
# back-beat.
_FOLK_BOOMCHICK_H = [
    [(0.0, 1.0, "root_5", 0.95), (1.0, 1.0, "top", 0.90),
     (2.0, 1.0, "root_5", 0.90), (3.0, 1.0, "top", 0.88)],
    [(0.0, 1.0, "root_5", 0.95),
     (1.0, 0.5, "top", 0.88), (1.5, 0.5, "top", 0.82),
     (2.0, 1.0, "root_5", 0.92),
     (3.0, 0.5, "top", 0.88), (3.5, 0.5, "top", 0.82)],
]
_FOLK_BOOMCHICK_B = [
    [(0.0, 1.0, "root"), (1.0, 1.0, "fifth"),
     (2.0, 1.0, "root"), (3.0, 1.0, "fifth")],
    [(0.0, 1.0, "root"), (1.0, 1.0, "fifth"),
     (2.0, 1.0, "third"), (3.0, 1.0, "fifth_up")],
    [(0.0, 0.5, "root"), (0.5, 0.5, "fifth"),
     (1.0, 0.5, "root"), (1.5, 0.5, "third"),
     (2.0, 0.5, "root"), (2.5, 0.5, "fifth"),
     (3.0, 0.5, "fifth"), (3.5, 0.5, "fifth_up")],
]
_FOLK_BOOMCHICK_P = [
    [(0.0, "tap", 0.50), (1.0, "brush", 0.65),
     (2.0, "tap", 0.45), (3.0, "brush", 0.65)],
    [(0.0, "tap", 0.50),
     (1.0, "brush", 0.65), (1.5, "brush", 0.45),
     (2.0, "tap", 0.45),
     (3.0, "brush", 0.65), (3.5, "brush", 0.45)],
    # folk-stomp
    [(0.0, "kick", 0.65), (1.0, "snare", 0.55),
     (2.0, "kick", 0.62), (3.0, "snare", 0.55)],
]

# folk → celtic (drone-heavy, Muji-Celtic core): held open-fifth
# voicings, drone bass, very sparse percussion. Pairs naturally with
# open_fifth voicing (already selected by arrange.py for folk INTRO/A).
_FOLK_CELTIC_H = [
    # drone — open fifth held all 4 beats
    [(0.0, 4.0, "root_5", 0.92)],
    # drone with single answer chord on beat 3
    [(0.0, 3.0, "root_5", 0.95), (3.0, 1.0, "top", 0.80)],
    # lilting pickup (existing folk alt 3)
    [(0.5, 0.5, "root_5", 0.85),
     (1.0, 1.5, "top",    0.92),
     (2.5, 1.5, "root_5", 0.88)],
]
_FOLK_CELTIC_B = [
    # full-bar root drone
    [(0.0, 4.0, "root")],
    # root + fifth half-bar pedal
    [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],
    # stepwise 1-3-5-1
    [(0.0, 1.0, "root"), (1.0, 1.0, "third"),
     (2.0, 1.0, "fifth"), (3.0, 1.0, "root")],
]
_FOLK_CELTIC_P = [
    # very sparse — single tap on 1
    [(0.0, "tap", 0.45)],
    [(0.0, "tap", 0.45), (2.0, "brush", 0.32)],
    # all-brush wash (no strong beats)
    [(0.0, "brush", 0.38), (1.0, "brush", 0.32),
     (2.0, "brush", 0.38), (3.0, "brush", 0.32)],
]

# jazz_ballad → walking (current default): walking quarter bass,
# ride+brush.
_JAZZ_WALKING_H = [
    [(0.0, 2.0, "top3", 0.90),
     (2.0, 0.5, "top",  0.80),
     (2.5, 1.5, "top3", 0.88)],
    [(0.0, 1.0, "top3", 0.90),
     (1.5, 0.5, "top",  0.80),
     (2.0, 1.0, "top3", 0.85),
     (3.5, 0.5, "top",  0.82)],
    [(0.0, 2.0, "top3", 0.90),
     (2.0, 2.0, "top3", 0.85)],
]
_JAZZ_WALKING_B = [
    [(0.0, 1.0, "root"), (1.0, 1.0, "third"),
     (2.0, 1.0, "fifth"), (3.0, 1.0, "third")],
    [(0.0, 1.0, "root"), (1.0, 1.0, "fifth_up"),
     (2.0, 1.0, "fifth"), (3.0, 1.0, "third")],
    # bebop straight-8ths
    [(0.0, 0.5, "root"), (0.5, 0.5, "third"),
     (1.0, 0.5, "fifth"), (1.5, 0.5, "fifth_up"),
     (2.0, 0.5, "fifth"), (2.5, 0.5, "third"),
     (3.0, 0.5, "fifth"), (3.5, 0.5, "fifth_up")],
]
_JAZZ_WALKING_P = [
    [(0.0, "ride", 0.40), (1.0, "brush", 0.55),
     (1.5, "ride", 0.30), (2.0, "ride", 0.40),
     (2.5, "ride", 0.30), (3.0, "brush", 0.55),
     (3.5, "ride", 0.30)],
    [(0.0, "brush", 0.45), (1.0, "brush", 0.55),
     (2.0, "brush", 0.45), (3.0, "brush", 0.55)],
]

# jazz_ballad → rubato (Bill Evans solo feel): whole-note chords,
# half-note bass, minimal percussion. Almost free time.
_JAZZ_RUBATO_H = [
    # whole-bar single chord — the "Bill Evans pause"
    [(0.0, 4.0, "top3", 0.88)],
    # 3-beat held + 1-beat answer
    [(0.0, 3.0, "top3", 0.88), (3.0, 1.0, "top", 0.78)],
    # two breathing stabs
    [(0.0, 2.0, "top3", 0.90), (2.0, 2.0, "top3", 0.85)],
]
_JAZZ_RUBATO_B = [
    # half-note root+fifth
    [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],
    # whole-bar root pedal
    [(0.0, 4.0, "root")],
    # pedal-then-walk (Bill Evans trio)
    [(0.0, 2.0, "root"), (2.0, 1.0, "fifth"), (3.0, 1.0, "third")],
]
_JAZZ_RUBATO_P = [
    # single brush on beat 1
    [(0.0, "brush", 0.40)],
    # brush on 1 and 3
    [(0.0, "brush", 0.40), (2.0, "brush", 0.35)],
    # ride on 2&4 only (super spacious)
    [(1.0, "ride", 0.40), (3.0, "ride", 0.40)],
]

# ── ambient → drone (Phase 1a 신규) ──────────────────────────────
# 깊은 sustained 드론. 베이스가 root 하나로 깔리고 화성은 호흡만,
# 타악기 거의 무음. 비/잔잔 날씨 ambient 곡에 적용.
_AMB_DRONE_H = [
    [(0.0, 4.0, "all", 1.00)],                                  # full-bar held
    [(0.0, 2.0, "all", 1.00), (2.0, 2.0, "top", 0.90)],          # 2-half breath
]
_AMB_DRONE_B = [
    [(0.0, 4.0, "root")],                                        # full-bar root drone
    [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],                   # gentle motion
]
_AMB_DRONE_P = [
    [],                                                          # truly silent
    [(0.0, "brush", 0.18)],                                      # heartbeat
]

# ── neo_classical → pedal (Phase 1a 신규) ────────────────────────
# 페달 포인트: 베이스가 root를 길게 누르고 화성이 그 위에서 움직임.
# 정적인 곡(잔잔한 날) 어울림.
_NEO_PEDAL_H = [
    [(0.0, 3.0, "all", 1.00), (3.0, 1.0, "top", 0.78)],          # 3-beat held + answer
    [(0.0, 4.0, "all", 0.95)],                                    # full-bar suspension
    [(0.0, 2.0, "all", 1.00), (2.0, 2.0, "top", 0.82)],          # block + arch
]
_NEO_PEDAL_B = [
    [(0.0, 4.0, "root")],                                         # full-bar root pedal
    [(0.0, 2.0, "root"), (2.0, 2.0, "fifth_up")],                # octave leap
]
_NEO_PEDAL_P = [
    [(0.0, "tap", 0.45)],                                         # tap on 1 only
    [(0.0, "tap", 0.45), (2.0, "tap", 0.32)],                    # 1+3 sparse
]

# ── lo_fi → boombap (Phase 1a 신규) ──────────────────────────────
# 무거운 kick + sub-bass 강조. half-time feel.
# 흐리고 어두운 날(wetness↑ brightness↓) 어울림.
_LOFI_BOOMBAP_H = [
    [(0.0, 4.0, "top", 0.85)],                                    # tape-hiss sustain
    [(0.5, 1.5, "top", 0.85), (2.5, 1.5, "top", 0.82)],          # lazy 2-hit
]
_LOFI_BOOMBAP_B = [
    [(0.0, 3.5, "root"), (3.5, 0.5, "fifth")],                   # 808 sustain
    [(0.0, 2.0, "root"), (2.0, 2.0, "fifth")],                   # half-note sub
]
_LOFI_BOOMBAP_P = [
    [(0.0, "kick", 0.78), (2.0, "snare", 0.62)],                 # half-time shell
    [(0.0, "kick", 0.75), (1.0, "hat", 0.28),
     (2.0, "snare", 0.60), (3.0, "hat", 0.28)],                  # + light hats
]


# Registry mapping (layer, genre, sub_style) → cell pack. Lookup is
# 4/4 only — sub-styles aren't defined for 3/4 / 6/8 yet (those meters
# are mostly folk and the celtic sub-style there isn't strongly distinct
# from boom_chick in 3 beats).
_SUB_PACKS = {
    "harmony": {
        ("bossa_nova",  "basica"):     _BOSSA_BASICA_H,
        ("bossa_nova",  "jazz"):       _BOSSA_JAZZ_H,
        ("folk",        "boom_chick"): _FOLK_BOOMCHICK_H,
        ("folk",        "celtic"):     _FOLK_CELTIC_H,
        ("jazz_ballad", "walking"):    _JAZZ_WALKING_H,
        ("jazz_ballad", "rubato"):     _JAZZ_RUBATO_H,
        ("ambient",       "drone"):    _AMB_DRONE_H,
        ("neo_classical", "pedal"):    _NEO_PEDAL_H,
        ("lo_fi",         "boombap"):  _LOFI_BOOMBAP_H,
    },
    "bass": {
        ("bossa_nova",  "basica"):     _BOSSA_BASICA_B,
        ("bossa_nova",  "jazz"):       _BOSSA_JAZZ_B,
        ("folk",        "boom_chick"): _FOLK_BOOMCHICK_B,
        ("folk",        "celtic"):     _FOLK_CELTIC_B,
        ("jazz_ballad", "walking"):    _JAZZ_WALKING_B,
        ("jazz_ballad", "rubato"):     _JAZZ_RUBATO_B,
        ("ambient",       "drone"):    _AMB_DRONE_B,
        ("neo_classical", "pedal"):    _NEO_PEDAL_B,
        ("lo_fi",         "boombap"):  _LOFI_BOOMBAP_B,
    },
    "percussion": {
        ("bossa_nova",  "basica"):     _BOSSA_BASICA_P,
        ("bossa_nova",  "jazz"):       _BOSSA_JAZZ_P,
        ("folk",        "boom_chick"): _FOLK_BOOMCHICK_P,
        ("folk",        "celtic"):     _FOLK_CELTIC_P,
        ("jazz_ballad", "walking"):    _JAZZ_WALKING_P,
        ("jazz_ballad", "rubato"):     _JAZZ_RUBATO_P,
        ("ambient",       "drone"):    _AMB_DRONE_P,
        ("neo_classical", "pedal"):    _NEO_PEDAL_P,
        ("lo_fi",         "boombap"):  _LOFI_BOOMBAP_P,
    },
}
