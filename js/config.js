// busy-day — client config
//
// SUPABASE_PUBLISHABLE_KEY is intentionally public; RLS protects the data.
// PASSWORD_HASH is the SHA-256 hex digest of the site password.
// Generate it locally with:
//   echo -n "yourpassword" | shasum -a 256
// then paste below. Empty = no gate (open access).

export const SUPABASE_URL = "https://diqxldieduslrpkjrguc.supabase.co";
export const SUPABASE_PUBLISHABLE_KEY =
  "sb_publishable_CT1j0VaiZjJDLfvDpbEzxQ_rlbi-6fT";
export const STORAGE_BUCKET = "busy-day-archive";

export const PASSWORD_HASH = ""; // sha-256 hex; empty disables the gate

export const DEFAULT_CITY = "seoul";
export const DEFAULT_CITY_NAME = "Seoul";
