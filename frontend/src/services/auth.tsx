import {
  createContext, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from 'react';
import type { Session } from '@supabase/supabase-js';
import { setRememberSession, supabase, supabaseConfigured } from './supabase';

type AuthContextValue = {
  configured: boolean;
  ready: boolean;
  session: Session | null;
  email: string | null;
  signIn: (email: string, password: string, remember: boolean) => Promise<void>;
  signUp: (name: string, email: string, password: string) => Promise<{ needsConfirmation: boolean }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!supabaseConfigured);
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    if (!supabase) return;
    const client = supabase;
    let mounted = true;

    client.auth.getSession().then(({ data, error }) => {
      if (!mounted) return;
      if (error) console.error('Unable to restore Supabase session.', error);
      setSession(data.session);
      setReady(true);
    }).catch((error: unknown) => {
      if (!mounted) return;
      console.error('Unable to restore Supabase session.', error);
      setReady(true);
    });

    const { data: sub } = client.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setReady(true);
    });

    const onUnauthorized = () => { void client.auth.signOut(); };
    window.addEventListener('quotegen:unauthorized', onUnauthorized);

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
      window.removeEventListener('quotegen:unauthorized', onUnauthorized);
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    configured: supabaseConfigured,
    ready,
    session,
    email: session?.user?.email ?? null,
    signIn: async (email, password, remember) => {
      const client = supabase;
      if (!client) throw new Error('Accounts are not enabled.');
      setRememberSession(remember);
      const { error } = await client.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
    },
    signUp: async (name, email, password) => {
      const client = supabase;
      if (!client) throw new Error('Accounts are not enabled.');
      const confirmationRedirect = new URL('/', window.location.origin);
      confirmationRedirect.searchParams.set('confirmed', '1');
      confirmationRedirect.searchParams.set('email', email);
      const { data, error } = await client.auth.signUp({
        email,
        password,
        options: {
          data: { full_name: name.trim() },
          emailRedirectTo: confirmationRedirect.toString(),
        },
      });
      if (error) throw new Error(error.message);
      return { needsConfirmation: !data.session };
    },
    signOut: async () => {
      const client = supabase;
      if (!client) return;
      const { error } = await client.auth.signOut();
      if (error) throw new Error(error.message);
    },
  }), [ready, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
