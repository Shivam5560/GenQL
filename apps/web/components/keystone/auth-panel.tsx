'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';

const GOTRUE_URL = process.env.NEXT_PUBLIC_GOTRUE_URL ?? 'http://localhost:9999';
const APP_ORIGIN = process.env.NEXT_PUBLIC_APP_ORIGIN ?? 'http://localhost:3000';

export type AuthMode = 'login' | 'register';

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#b0602f] focus-visible:ring-offset-2 focus-visible:ring-offset-[#f7f4ee]';

const field =
  'w-full border border-[#16181a]/20 bg-[#fbf9f5] px-3.5 py-2.5 text-[14px] text-[#16181a] outline-none transition-colors placeholder:text-[#16181a]/35 focus:border-[#b0602f]';

const label = 'text-[10px] uppercase tracking-[0.16em] text-[#16181a]/50';

/**
 * The sign-in overlay, opened from the header and from the hero's CTAs.
 *
 * Square corners, paper ground, one bronze accent — the entry screen's own
 * language rather than the workspace's rounded components, because it sits on
 * top of the entry screen and would read as a foreign object otherwise.
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
      className="fixed inset-0 z-[90] flex items-center justify-center px-5 py-8"
      style={{ background: 'rgba(22,24,26,0.42)', backdropFilter: 'blur(6px)' }}
      onMouseDown={(event) => {
        if (!dialogRef.current?.contains(event.target as Node)) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={mode === 'login' ? 'Sign in to GenQL' : 'Create a GenQL account'}
        className="ks-reveal ks-reveal-in max-h-full w-full max-w-[420px] overflow-y-auto border border-[#16181a]/15 bg-[#f7f4ee] p-7 shadow-[0_40px_90px_-40px_rgba(22,24,26,0.6)]"
      >
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <p className={label} style={{ fontFamily: 'var(--font-eyebrow)' }}>
              GenQL
            </p>
            <h2 className="mt-2 font-serif text-[30px] leading-[1.05] tracking-[-0.02em] text-[#16181a]">
              {mode === 'login' ? 'Sign in.' : 'Create an account.'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className={`shrink-0 border border-[#16181a]/20 px-2.5 py-1 text-[11px] text-[#16181a]/55 transition-colors hover:text-[#16181a] ${focusRing}`}
          >
            Esc
          </button>
        </div>

        {error && (
          <p
            role="alert"
            className="mb-5 border-l-2 border-[#b0602f] bg-[#b0602f]/[0.07] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#16181a]"
          >
            {error}
          </p>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label
              className={label}
              style={{ fontFamily: 'var(--font-eyebrow)' }}
              htmlFor="auth-email"
            >
              Email
            </label>
            <input
              ref={firstFieldRef}
              id="auth-email"
              name="email"
              type="email"
              required
              autoComplete="email"
              className={`${field} ${focusRing}`}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label
              className={label}
              style={{ fontFamily: 'var(--font-eyebrow)' }}
              htmlFor="auth-password"
            >
              Password
            </label>
            <input
              id="auth-password"
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className={`${field} ${focusRing}`}
            />
          </div>
          {mode === 'register' && (
            <div className="flex flex-col gap-1.5">
              <label
                className={label}
                style={{ fontFamily: 'var(--font-eyebrow)' }}
                htmlFor="auth-confirmation"
              >
                Confirm password
              </label>
              <input
                id="auth-confirmation"
                name="confirmation"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                className={`${field} ${focusRing}`}
              />
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className={`mt-1 flex items-center justify-center gap-3 bg-[#16181a] px-6 py-3.5 text-[11px] uppercase tracking-[0.16em] text-[#f7f4ee] transition-colors hover:bg-[#2c2f32] disabled:opacity-60 ${focusRing}`}
            style={{ fontFamily: 'var(--font-eyebrow)' }}
          >
            {busy
              ? mode === 'login'
                ? 'Signing in…'
                : 'Creating…'
              : mode === 'login'
                ? 'Enter GenQL'
                : 'Create account'}
            <span aria-hidden className="h-[5px] w-[5px] bg-[#b0602f]" />
          </button>
        </form>

        <div className="my-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-[#16181a]/12" />
          <span className={label} style={{ fontFamily: 'var(--font-eyebrow)' }}>
            or
          </span>
          <span className="h-px flex-1 bg-[#16181a]/12" />
        </div>

        <div className="flex flex-col gap-2.5">
          <a
            href={oauth('google')}
            className={`flex items-center justify-center border border-[#16181a]/20 px-5 py-3 text-[11px] uppercase tracking-[0.14em] text-[#16181a]/75 transition-colors hover:border-[#16181a]/45 hover:text-[#16181a] ${focusRing}`}
            style={{ fontFamily: 'var(--font-eyebrow)' }}
          >
            Continue with Google
          </a>
          <a
            href={oauth('github')}
            className={`flex items-center justify-center border border-[#16181a]/20 px-5 py-3 text-[11px] uppercase tracking-[0.14em] text-[#16181a]/75 transition-colors hover:border-[#16181a]/45 hover:text-[#16181a] ${focusRing}`}
            style={{ fontFamily: 'var(--font-eyebrow)' }}
          >
            Continue with GitHub
          </a>
        </div>

        <p className="mt-6 text-center text-[13px] text-[#16181a]/60">
          {mode === 'login' ? 'No account yet? ' : 'Already have an account? '}
          <button
            type="button"
            onClick={() => {
              setError('');
              onModeChange(mode === 'login' ? 'register' : 'login');
            }}
            className={`underline underline-offset-2 hover:text-[#16181a] ${focusRing}`}
          >
            {mode === 'login' ? 'Create one' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  );
}
