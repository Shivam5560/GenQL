'use client';

import { useEffect, useState } from 'react';

export default function OAuthCallbackPage() {
  const [error, setError] = useState(false);

  useEffect(() => {
    // Every failure path — including a missing fragment token — resolves
    // asynchronously, so the effect body never sets state synchronously.
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const refreshToken = params.get('refresh_token');
    void (async () => {
      try {
        if (!refreshToken) throw new Error('no refresh_token in callback fragment');
        const response = await fetch('/api/auth/callback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) throw new Error('callback exchange failed');
        // A full reload (not router.push) so AuthProvider's mount-time
        // refresh picks up the now-set cookie from a clean slate — it
        // otherwise has no way to know a new cookie just appeared.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- intentional full reload; router.push would leave AuthProvider unaware of the new cookie
        window.location.href = '/';
      } catch {
        setError(true);
      }
    })();
  }, []);

  if (error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-[var(--mute)]">Sign-in did not complete. Try again.</p>
        <a className="text-sm underline" href="/login">Back to sign in</a>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-4 px-6">
      <p className="text-sm text-[var(--mute)]">Signing you in…</p>
    </main>
  );
}
