import { useState, type FormEvent } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useAuth } from '../services/auth';
import { PasswordField } from './PasswordField';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Props {
  initialEmail?: string;
  initialMode?: 'signin' | 'signup';
  /** Shown above the form to explain why the visitor was sent here. */
  intentLabel?: string;
  onBack?: () => void;
}

/** Turn Supabase's raw errors into friendly, actionable copy. */
function friendlyError(message: string, mode: 'signin' | 'signup'): string {
  const lower = message.toLowerCase();
  if (lower.includes('already registered') || lower.includes('already been registered')
    || lower.includes('user already exists')) {
    return 'An account with this email already exists. Try signing in instead.';
  }
  if (lower.includes('invalid login credentials')) {
    return 'Email or password is incorrect.';
  }
  if (lower.includes('email not confirmed')) {
    return 'Please confirm your email address first, then sign in.';
  }
  if (lower.includes('unable to validate email') || lower.includes('invalid email')
    || lower.includes('email address is invalid')) {
    return 'That email address does not look valid.';
  }
  if (lower.includes('password should be at least') || lower.includes('password is too short')) {
    return 'Your password is too short. Use at least 6 characters.';
  }
  if (lower.includes('rate limit') || lower.includes('too many')) {
    return 'Too many attempts. Please wait a moment and try again.';
  }
  return message || (mode === 'signin' ? 'Unable to sign in.' : 'Unable to create your account.');
}

export function LoginPage({
  initialEmail = '', initialMode = 'signin', intentLabel = '', onBack,
}: Props) {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>(initialMode);
  const [name, setName] = useState('');
  const [email, setEmail] = useState(initialEmail);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const trimmedEmail = email.trim();
  const emailValid = EMAIL_RE.test(trimmedEmail);
  const passwordValid = password.length >= 6;
  const nameValid = name.trim().length > 0;
  const mismatch = mode === 'signup' && confirm.length > 0 && password !== confirm;

  const canSubmit = mode === 'signin'
    ? emailValid && password.length > 0
    : nameValid && emailValid && passwordValid && confirm.length > 0 && password === confirm;

  const switchMode = (next: 'signin' | 'signup') => {
    setMode(next);
    setError('');
    setNotice('');
    setConfirm('');
    setSubmitted(false);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setSubmitted(true);
    if (mode === 'signup' && password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    if (!canSubmit) return;
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signIn(trimmedEmail, password, remember);
      } else {
        // Only the original password is ever sent to Supabase; the confirmation
        // field is validated here and discarded.
        const { needsConfirmation } = await signUp(name.trim(), trimmedEmail, password);
        setNotice(
          needsConfirmation
            ? 'Account created. Check your inbox to confirm your email, then sign in.'
            : 'Account created. You are now signed in.',
        );
        if (needsConfirmation) {
          setPassword('');
          setConfirm('');
          setMode('signin');
        }
      }
    } catch (err) {
      setError(friendlyError(err instanceof Error ? err.message : '', mode));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[var(--bg)]">
      <div className="card w-full max-w-sm">
        {onBack && (
          <button
            type="button"
            className="btn btn-ghost text-xs -ml-2 mb-2"
            onClick={onBack}
          >
            <ArrowLeft size={14} /> Back to site
          </button>
        )}
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-lg">quoteGEN</span>
          <span className="chip chip-gold">AI</span>
        </div>
        <p className="text-sm text-[var(--text-muted)] mb-5">
          {mode === 'signin'
            ? 'Sign in to your quotations.'
            : 'Create your quoteGEN AI account.'}
        </p>
        {intentLabel && (
          <p className="panel p-3 text-xs text-[var(--text-muted)] mb-4">{intentLabel}</p>
        )}

        <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
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
                style={submitted && !nameValid ? { borderColor: 'var(--error)' } : undefined}
              />
            </label>
          )}

          <label className="flex flex-col gap-1">
            <span className="label">Email address</span>
            <input
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@business.com"
              style={submitted && !emailValid ? { borderColor: 'var(--error)' } : undefined}
            />
            {submitted && !emailValid && (
              <span className="text-xs text-[var(--error)]">Enter a valid email address.</span>
            )}
          </label>

          <PasswordField
            label="Password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            placeholder="At least 6 characters"
            minLength={6}
            invalid={submitted && mode === 'signup' && !passwordValid}
          />
          {submitted && mode === 'signup' && !passwordValid && (
            <span className="text-xs text-[var(--error)] -mt-2">
              Password must be at least 6 characters.
            </span>
          )}

          {mode === 'signup' && (
            <PasswordField
              label="Retype password"
              value={confirm}
              onChange={setConfirm}
              autoComplete="new-password"
              placeholder="Re-enter your password"
              invalid={mismatch}
            />
          )}
          {mismatch && (
            <span className="text-xs text-[var(--error)] -mt-2">Passwords do not match.</span>
          )}
          {mode === 'signup' && confirm.length > 0 && !mismatch && (
            <span className="text-xs text-[var(--ok,#2e7d32)] -mt-2">Passwords match.</span>
          )}

          {mode === 'signin' && (
            <label className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
              />
              Remember me on this device
            </label>
          )}

          {error && <p role="alert" className="text-sm text-[var(--danger,#c0392b)]">{error}</p>}
          {notice && <p className="text-sm text-[var(--ok,#2e7d32)]">{notice}</p>}

          <button type="submit" className="btn btn-primary mt-1" disabled={busy || !canSubmit}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <button
          type="button"
          className="btn btn-ghost w-full mt-3 text-sm"
          onClick={() => switchMode(mode === 'signin' ? 'signup' : 'signin')}
        >
          {mode === 'signin'
            ? "Don't have an account? Sign up"
            : 'Already have an account? Sign in'}
        </button>
      </div>
    </div>
  );
}
