-- busy-day: initial schema (single-user, weather + genre composer)
--
-- Storage convention (bucket: busy-day-archive, public read):
--   {city}/{YYYY}/{MM}/{date}/
--     ir.json  musicxml  score.jpg
--     audio_short.mp3   audio_short.wav
--     audio_long.mp3    audio_long.wav
--     audio.mid  meta.json

create extension if not exists pgcrypto;

-- ── reference: cities ──────────────────────────────────────────
create table if not exists public.cities (
  id        text primary key,            -- 'seoul', 'tokyo'
  name      text not null,
  lat       double precision not null,
  lon       double precision not null,
  kma_nx    int,                         -- KMA LCC grid (nullable for non-KR)
  kma_ny    int,
  tz        text not null default 'Asia/Seoul',
  created_at timestamptz not null default now()
);

-- ── motif pool (human seed + weekly LLM additions in v1.1) ─────
create table if not exists public.motif_pool (
  id          text primary key,           -- 'm_2026w19_03'
  added_week  text not null,              -- ISO '2026-W19'
  source      text not null,              -- 'human_seed' | 'llm_v1.1'
  contour     jsonb not null,             -- {pitches:[…], rhythm:[…]}
  tags        text[] not null default '{}',
  active      boolean not null default true,
  created_at  timestamptz not null default now()
);

create index if not exists motif_pool_active_idx
  on public.motif_pool (active, added_week desc);

-- ── weekly theme (long-form variation) ─────────────────────────
create table if not exists public.weekly_theme (
  iso_week         text primary key,      -- '2026-W19'
  preferred_genre  text not null,         -- 'ambient'|'bossa_nova'|...
  palette          jsonb not null,        -- instrument/eq biases
  notes            text,
  created_at       timestamptz not null default now()
);

-- ── songs ──────────────────────────────────────────────────────
create table if not exists public.songs (
  id                 uuid primary key default gen_random_uuid(),
  city_id            text not null references public.cities(id),
  date               date not null,
  seed               bigint not null,

  key_root           text not null,        -- 'D'
  mode               text not null,        -- 'ionian'|'dorian'|'lydian'|'mixolydian'
  genre              text not null,        -- 'ambient'|'bossa_nova'|'jazz_ballad'|'lo_fi'|'neo_classical'|'folk'
  bpm                int  not null,
  meter              text not null,        -- '3/4'|'4/4'|'6/8'

  duration_short_sec int  not null,        -- target ~60
  duration_long_sec  int  not null,        -- target ~135

  weather            jsonb not null,       -- raw KMA snapshot
  features           jsonb not null,       -- {warmth,brightness,wetness,calmness}

  signature          text not null,        -- hash for 14d hard-ban
  start_pitch        text not null,        -- 'D4' for 5d avoidance
  motif_id           text not null references public.motif_pool(id),
  week_theme         text not null references public.weekly_theme(iso_week),

  quality            jsonb,                -- regression test scores
  paths              jsonb not null,       -- {ir, musicxml, jpg,
                                            --  mp3_short, mp3_long,
                                            --  wav_short, wav_long, midi}

  generator_ver      text not null,        -- 'v1.0.0'
  created_at         timestamptz not null default now(),

  unique (city_id, date, generator_ver)
);

create index if not exists songs_city_date_idx
  on public.songs (city_id, date desc);

create index if not exists songs_signature_recent_idx
  on public.songs (city_id, signature, date desc);

create index if not exists songs_motif_recent_idx
  on public.songs (city_id, motif_id, date desc);

create index if not exists songs_genre_recent_idx
  on public.songs (city_id, genre, date desc);

create index if not exists songs_weather_gin_idx
  on public.songs using gin (weather);

-- ── plays (single-user; no user_id) ────────────────────────────
create table if not exists public.plays (
  id           uuid primary key default gen_random_uuid(),
  song_id      uuid not null references public.songs(id) on delete cascade,
  played_at    timestamptz not null default now(),
  variant      text not null check (variant in ('short','long')),
  completed    boolean not null default false,
  liked        boolean not null default false
);

create index if not exists plays_song_idx on public.plays (song_id, played_at desc);

-- ── RLS: songs/cities/themes public-read; plays insert-anyone ──
alter table public.cities       enable row level security;
alter table public.songs        enable row level security;
alter table public.plays        enable row level security;
alter table public.motif_pool   enable row level security;
alter table public.weekly_theme enable row level security;

create policy "cities readable by anyone"
  on public.cities for select using (true);

create policy "songs readable by anyone"
  on public.songs for select using (true);

create policy "weekly_theme readable by anyone"
  on public.weekly_theme for select using (true);

-- motif_pool: read-only to public; writes only via service role
create policy "motif_pool readable by anyone"
  on public.motif_pool for select using (true);

-- plays: anyone can insert/select their own play log (single-user app, no auth)
create policy "plays insert by anyone"
  on public.plays for insert with check (true);

create policy "plays readable by anyone"
  on public.plays for select using (true);
