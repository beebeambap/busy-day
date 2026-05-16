-- Pin column: null = no opinion, 'legendary' = best, 'worst' = hide by default.
ALTER TABLE songs
  ADD COLUMN IF NOT EXISTS pin_type text
  CHECK (pin_type IN ('legendary', 'worst'));
