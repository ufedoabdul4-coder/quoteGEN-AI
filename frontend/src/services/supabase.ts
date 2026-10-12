import { createClient, type SupabaseClient } from '@supabase/supabase-js';

// Supabase is optional: when the project is not configured (local development
// without accounts) the app runs in a single-user, no-login mode instead.
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
const REMEMBER_SESSION_KEY = 'quotegen:remember-session';

const authStorage = {
  getItem: async (key: string) => {
    const preference = localStorage.getItem(REMEMBER_SESSION_KEY);
    const remember = preference === 'true'
      || (preference === null && localStorage.getItem(key) !== null);
    const storage = remember
      ? localStorage
      : sessionStorage;
    return storage.getItem(key);
  },
  setItem: async (key: string, value: string) => {
    const preference = localStorage.getItem(REMEMBER_SESSION_KEY);
    const remember = preference === 'true'
      || (preference === null && localStorage.getItem(key) !== null);
    const storage = remember ? localStorage : sessionStorage;
    const otherStorage = remember ? sessionStorage : localStorage;
    storage.setItem(key, value);
    otherStorage.removeItem(key);
  },
  removeItem: async (key: string) => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  },
};

export function setRememberSession(remember: boolean): void {
  localStorage.setItem(REMEMBER_SESSION_KEY, String(remember));
}

export const supabase: SupabaseClient | null =
  url && anonKey
    ? createClient(url, anonKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
        storage: authStorage,
      },
    })
    : null;

export const supabaseConfigured = Boolean(supabase);
