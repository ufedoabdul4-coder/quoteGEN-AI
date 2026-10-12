import { useState, type FormEvent } from 'react';
import { useAuth } from '../services/auth';

export function LoginPage({ initialEmail = '' }: { initialEmail?: string }) {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signIn(email.trim(), password);
      } else {
        const { needsConfirmation } = await signUp(name.trim(), email.trim(), password);
        if (needsConfirmation) {
          setNotice('Check your inbox to confirm your email, then sign in.');
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[var(--bg)]">
      <div className="card w-full max-w-sm">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-lg">quoteGEN</span>
          <span className="chip chip-gold">AI</span>
        </div>
        <p className="text-sm text-[var(--text-muted)] mb-5">
          {mode === 'signin' ? 'Sign in to your quotations.' : 'Create an account to get started.'}
        </p>

        <form onSubmit={submit} className="flex flex-col gap-3">
          {mode === 'signup' && (
            <label className="flex flex-col gap-1">
              <span className="label">Full name</span>
              <input
                className="input"
                type="text"
                autoComplete="name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
              />
            </label>
          )}

          <label className="flex flex-col gap-1">
            <span className="label">Email</span>
            <input
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@business.com"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="label">Password</span>
            <input
              className="input"
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
            />
          </label>

          {error && <p className="text-sm text-[var(--danger,#c0392b)]">{error}</p>}
          {notice && <p className="text-sm text-[var(--ok,#2e7d32)]">{notice}</p>}

          <button type="submit" className="btn btn-primary mt-1" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <button
          type="button"
          className="btn btn-ghost w-full mt-3 text-sm"
          onClick={() => {
            setMode(mode === 'signin' ? 'signup' : 'signin');
            setError('');
            setNotice('');
          }}
        >
          {mode === 'signin'
            ? "Don't have an account? Sign up"
            : 'Already have an account? Sign in'}
        </button>
      </div>
    </div>
  );
}
