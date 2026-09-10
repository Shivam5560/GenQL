'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';

const GOTRUE_URL = process.env.NEXT_PUBLIC_GOTRUE_URL ?? 'http://localhost:9999';
const APP_ORIGIN = process.env.NEXT_PUBLIC_APP_ORIGIN ?? 'http://localhost:3000';

export type AuthMode = 'login' | 'register';

const field =
  'w-full border border-[var(--line)] bg-[var(--panel-2)] px-3.5 py-2.5 text-[14px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--mute)] focus:border-[var(--brand)]';

const label = 'font-eyebrow text-[10px] uppercase tracking-[0.16em] text-[var(--mute)]';

/**
 * The sign-in overlay, opened from the header and from the hero's CTAs.
 *
 * Errors are stated in the panel, above the form, and never as a toast: a
 * message about the field you are looking at should not appear in the corner
 * of the screen and then leave.
 */
export function AuthPanel({
  mode,
  onModeChange,
  onClose,
}: {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onClose: () => void;
}) {
  const { login, signup } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, [mode]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get('email'));
    const password = String(data.get('password'));

    if (mode === 'register' && password !== String(data.get('confirmation'))) {
      setError('Those passwords do not match.');
      return;
    }

    setBusy(true);
    setError('');
    try {
      if (mode === 'login') await login(email, password);
      else await signup(email, password);
      router.push('/');
    } catch {
      setError(
        mode === 'login'
          ? 'That email and password did not match an account.'
          : 'An account could not be created with that email. It may already exist.',
      );
    } finally {
      setBusy(false);
    }
  }

  const oauth = (provider: 'google' | 'github') =>
    `${GOTRUE_URL}/authorize?provider=${provider}&redirect_to=${encodeURIComponent(`${APP_ORIGIN}/callback`)}`;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 px-5 py-8 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (!dialogRef.current?.contains(event.target as Node)) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={mode === 'login' ? 'Sign in to GenQL' : 'Create a GenQL account'}
        className="gq-rise max-h-full w-full max-w-[420px] overflow-y-auto border border-[var(--line)] bg-[var(--panel)] p-7 shadow-[0_40px_90px_-40px_rgba(0,0,0,0.7)]"
      >
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <p className={label}>GenQL</p>
            <h2 className="mt-2 font-serif text-[30px] font-light leading-[1.05] tracking-[-0.02em]">
              {mode === 'login' ? 'Sign in.' : 'Create an account.'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 border border-[var(--line)] px-2.5 py-1 text-[11px] text-[var(--mute)] transition-colors hover:text-[var(--ink)]"
          >
            Esc
          </button>
        </div>

        {error && (
          <p
            role="alert"
            className="mb-5 border-l-2 border-[var(--brand)] bg-[var(--brand)]/10 px-3.5 py-2.5 text-[13px] leading-relaxed text-[var(--ink)]"
          >
            {error}
          </p>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className={label} htmlFor="auth-email">
              Email
            </label>
            <input
              ref={firstFieldRef}
              id="auth-email"
              name="email"
              type="email"
              required
              autoComplete="email"
              className={field}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className={label} htmlFor="auth-password">
              Password
            </label>
            <input
              id="auth-password"
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className={field}
            />
          </div>
          {mode === 'register' && (
            <div className="flex flex-col gap-1.5">
              <label className={label} htmlFor="auth-confirmation">
                Confirm password
              </label>
              <input
                id="auth-confirmation"
                name="confirmation"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                className={field}
              />
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="mt-1 flex items-center justify-center gap-3 bg-[var(--brand)] px-6 py-3.5 font-eyebrow text-[11px] uppercase tracking-[0.16em] text-[var(--brand-ink)] transition-colors disabled:opacity-60"
          >
            {busy
              ? mode === 'login'
                ? 'Signing in…'
                : 'Creating…'
              : mode === 'login'
                ? 'Enter GenQL'
                : 'Create account'}
          </button>
        </form>

        <div className="my-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-[var(--line)]" />
          <span className={label}>or</span>
          <span className="h-px flex-1 bg-[var(--line)]" />
        </div>

        <div className="flex flex-col gap-2.5">
          <a
            href={oauth('google')}
            className="flex items-center justify-center border border-[var(--line)] px-5 py-3 font-eyebrow text-[11px] uppercase tracking-[0.14em] text-[var(--mute)] transition-colors hover:border-[var(--brand)] hover:text-[var(--ink)]"
          >
            Continue with Google
          </a>
          <a
            href={oauth('github')}
            className="flex items-center justify-center border border-[var(--line)] px-5 py-3 font-eyebrow text-[11px] uppercase tracking-[0.14em] text-[var(--mute)] transition-colors hover:border-[var(--brand)] hover:text-[var(--ink)]"
          >
            Continue with GitHub
          </a>
        </div>

        <p className="mt-6 text-center text-[13px] text-[var(--mute)]">
          {mode === 'login' ? 'No account yet? ' : 'Already have an account? '}
          <button
            type="button"
            onClick={() => {
              setError('');
              onModeChange(mode === 'login' ? 'register' : 'login');
            }}
            className="text-[var(--ink)] underline underline-offset-2 hover:text-[var(--brand)]"
          >
            {mode === 'login' ? 'Create one' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  );
}
