'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function OAuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const refreshToken = params.get('refresh_token');
    if (!refreshToken) {
      setError(true);
      return;
    }
    fetch('/api/auth/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then((response) => {
        if (!response.ok) throw new Error('callback exchange failed');
        // A full reload (not router.push) so AuthProvider's mount-time
        // refresh picks up the now-set cookie from a clean slate — it
        // otherwise has no way to know a new cookie just appeared.
        window.location.href = '/';
      })
      .catch(() => setError(true));
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
