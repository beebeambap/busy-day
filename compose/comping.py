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
                        section: str, rng: Random):
    bpb = int(meter.split("/")[0])
    h, _ = _table(bpb)
    cells = h.get(genre, h["ambient"])
    return _maybe_drop_last(_pick_cell(cells, section, rng), rng)


def bass_pattern_for(genre: str, meter: str,
                     section: str, rng: Random):
    bpb = int(meter.split("/")[0])
    _, b = _table(bpb)
    cells = b.get(genre, b["ambient"])
    return _maybe_drop_last(_pick_cell(cells, section, rng), rng, p=0.08)


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
    "ambient":      [
        [],
        [],
    ],
    "neo_classical": [
        [(0.0, "tap", 0.55), (2.0, "tap", 0.45)],
        [(0.0, "tap", 0.55), (1.5, "brush", 0.40), (2.0, "tap", 0.45)],
    ],
    "folk": [
        [(0.0, "tap", 0.50), (1.0, "brush", 0.65),
         (2.0, "tap", 0.45), (3.0, "brush", 0.65)],
        # alt: double-brush on 2 & 4 for emphasis
        [(0.0, "tap", 0.50),
         (1.0, "brush", 0.65), (1.5, "brush", 0.45),
         (2.0, "tap", 0.45),
         (3.0, "brush", 0.65), (3.5, "brush", 0.45)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
         (1.0, "shaker", 0.55), (1.5, "shaker", 0.40),
         (2.0, "shaker", 0.55), (2.5, "shaker", 0.40),
         (3.0, "shaker", 0.55), (3.5, "shaker", 0.40)],
        # alt: tap on 1 + 3, lighter shaker between
        [(0.0, "tap",    0.55),
         (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
         (1.5, "shaker", 0.35),
         (2.0, "tap",    0.50),
         (2.5, "shaker", 0.35), (3.0, "shaker", 0.45),
         (3.5, "shaker", 0.35)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (1.0, "brush", 0.55),
         (1.5, "ride", 0.30), (2.0, "ride", 0.40),
         (2.5, "ride", 0.30), (3.0, "brush", 0.55),
         (3.5, "ride", 0.30)],
        # alt: brushes only — softer chorus-like feel
        [(0.0, "brush", 0.45), (1.0, "brush", 0.55),
         (2.0, "brush", 0.45), (3.0, "brush", 0.55)],
    ],
    "lo_fi": [
        [(0.0, "kick",  0.75),
         (0.5, "hat",   0.30), (1.0, "hat", 0.30), (1.5, "hat", 0.30),
         (2.0, "snare", 0.65),
         (2.5, "hat",   0.30), (3.0, "hat", 0.30), (3.5, "hat", 0.30)],
        # alt: kick on 1+2.5 (syncopated), snare 3
        [(0.0, "kick",  0.75),
         (0.5, "hat",   0.30), (1.0, "hat", 0.30), (1.5, "hat", 0.30),
         (2.0, "snare", 0.60),
         (2.5, "kick",  0.55), (3.0, "hat", 0.30), (3.5, "hat", 0.30)],
    ],
}

_P34 = {
    "ambient":      [[], []],
    "neo_classical": [
        [(0.0, "tap", 0.55)],
        [(0.0, "tap", 0.55), (2.0, "tap", 0.40)],
    ],
    "folk": [
        [(0.0, "tap", 0.55), (1.0, "brush", 0.55), (2.0, "brush", 0.55)],
        [(0.0, "tap", 0.55), (1.0, "brush", 0.55),
         (1.5, "brush", 0.40), (2.0, "brush", 0.55)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (0.5, "shaker", 0.40),
         (1.0, "shaker", 0.50), (1.5, "shaker", 0.40),
         (2.0, "shaker", 0.50), (2.5, "shaker", 0.40)],
        [(0.0, "tap",    0.50),
         (0.5, "shaker", 0.35), (1.0, "shaker", 0.45),
         (1.5, "shaker", 0.35), (2.0, "shaker", 0.45),
         (2.5, "shaker", 0.35)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (1.0, "brush", 0.55), (2.0, "ride", 0.40)],
        [(0.0, "brush", 0.45), (1.0, "brush", 0.55), (2.0, "brush", 0.45)],
    ],
    "lo_fi": [
        [(0.0, "kick", 0.70), (1.0, "snare", 0.55), (2.0, "snare", 0.55)],
        [(0.0, "kick", 0.70), (1.5, "snare", 0.55),
         (2.0, "hat", 0.30), (2.5, "hat", 0.30)],
    ],
}

_P68 = {
    "ambient":      [[], []],
    "neo_classical": [
        [(0.0, "tap", 0.55), (3.0, "tap", 0.45)],
        [(0.0, "tap", 0.55), (3.0, "brush", 0.40)],
    ],
    "folk": [
        [(0.0, "tap", 0.55), (3.0, "brush", 0.60)],
        [(0.0, "tap", 0.55), (1.5, "brush", 0.40),
         (3.0, "brush", 0.60), (4.5, "brush", 0.40)],
    ],
    "bossa_nova": [
        [(0.0, "shaker", 0.55), (1.0, "shaker", 0.40),
         (2.0, "shaker", 0.40), (3.0, "shaker", 0.55),
         (4.0, "shaker", 0.40), (5.0, "shaker", 0.40)],
        [(0.0, "tap",    0.50),
         (1.0, "shaker", 0.35), (2.0, "shaker", 0.35),
         (3.0, "tap",    0.50),
         (4.0, "shaker", 0.35), (5.0, "shaker", 0.35)],
    ],
    "jazz_ballad": [
        [(0.0, "ride", 0.40), (3.0, "ride", 0.40),
         (1.5, "brush", 0.45), (4.5, "brush", 0.45)],
        [(0.0, "brush", 0.45), (3.0, "brush", 0.55)],
    ],
    "lo_fi": [
        [(0.0, "kick", 0.70), (3.0, "snare", 0.55)],
        [(0.0, "kick", 0.70), (1.5, "hat", 0.30),
         (3.0, "snare", 0.55), (4.5, "hat", 0.30)],
    ],
}


def percussion_pattern_for(genre: str, meter: str,
                           section: str, rng: Random):
    bpb = int(meter.split("/")[0])
    table = {3: _P34, 4: _P44, 6: _P68}.get(bpb, _P44)
    cells = table.get(genre, [[]])
    return _pick_cell(cells, section, rng)


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
