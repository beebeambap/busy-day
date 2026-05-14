-- Weather Tapes — theme-album arrangement variants
--
-- A "tape" is a fixed-rule re-arrangement of an existing song,
-- triggered by the user from the calendar (per-weather button).
-- The arrangement preserves the original song's key, melody pitches,
-- and chord-degree progression but transforms voicing, comping,
-- instrumentation, tempo, and groove according to a per-weather preset.
--
-- Data model: tapes live in the same `songs` table as a new
-- variant_id (e.g. "rain_tape", "clear_hot_tape"). Two new columns:
--   tape_id         — the preset that produced this variant
--                     (NULL = original / non-tape variant)
--   source_song_id  — the original song this tape was derived from
--                     (NULL for originals; FK to songs.id for tapes)
--
-- The existing UNIQUE (city_id, date, generator_ver, variant_id)
-- already supports multiple tape variants per date without conflict.

ALTER TABLE public.songs
  ADD COLUMN IF NOT EXISTS tape_id text,
  ADD COLUMN IF NOT EXISTS source_song_id uuid REFERENCES public.songs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS songs_tape_idx
  ON public.songs (city_id, tape_id, date DESC)
  WHERE tape_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS songs_source_song_idx
  ON public.songs (source_song_id)
  WHERE source_song_id IS NOT NULL;
