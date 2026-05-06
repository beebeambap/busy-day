-- busy-day: initial schema
-- songs(): one row per generated daily song; ir.json + audio paths
-- live in Supabase Storage (bucket: busy-day-archive).

create extension if not exists pgcrypto;

create table if not exists public.cities (
  id        text primary key,            -- 'seoul', 'tokyo'
  name      text not null,
  lat       double precision not null,
  lon       double precision not null,
  tz        text not null default 'Asia/Seoul',
  created_at timestamptz not null default now()
);

create table if not exists public.songs (
  id             uuid primary key default gen_random_uuid(),
  city_id        text not null references public.cities(id),
  date           date not null,
  seed           bigint not null,
  key_root       text not null,                 -- 'D'
  mode           text not null,                 -- 'dorian' | 'ionian' | ...
  bpm            int  not null,
  duration_sec   int  not null,
  weather        jsonb not null,                -- raw KMA snapshot
  features       jsonb not null,                -- normalized {warmth, brightness, ...}
  quality        jsonb,                         -- regression-test scores
  paths          jsonb not null,                -- {ir, musicxml, jpg, mp3, wav, midi}
  generator_ver  text not null,                 -- 'v1.2.0'
  created_at     timestamptz not null default now(),
  unique (city_id, date, generator_ver)
);

create index if not exists songs_city_date_idx
  on public.songs (city_id, date desc);

create index if not exists songs_weather_gin_idx
  on public.songs using gin (weather);

create table if not exists public.plays (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid,                            -- nullable: anonymous plays ok
  song_id      uuid not null references public.songs(id) on delete cascade,
  played_at    timestamptz not null default now(),
  duration_sec int not null default 0,
  liked        boolean not null default false
);

create index if not exists plays_song_idx on public.plays (song_id);
create index if not exists plays_user_idx on public.plays (user_id, played_at desc);

-- RLS: songs are public-read; plays are owner-scoped.
alter table public.cities enable row level security;
alter table public.songs  enable row level security;
alter table public.plays  enable row level security;

create policy "cities readable by anyone"
  on public.cities for select
  using (true);

create policy "songs readable by anyone"
  on public.songs for select
  using (true);

create policy "plays insert by anyone"
  on public.plays for insert
  with check (true);

create policy "plays readable by owner"
  on public.plays for select
  using (auth.uid() is not null and user_id = auth.uid());
