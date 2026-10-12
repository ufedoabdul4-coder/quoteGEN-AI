import { createClient, type SupabaseClient } from '@supabase/supabase-js';

// Supabase is optional: when the project is not configured (local development
// without accounts) the app runs in a single-user, no-login mode instead.
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export const supabaseConfigured = Boolean(supabase);
