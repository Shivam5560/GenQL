'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const GOTRUE_URL = process.env.NEXT_PUBLIC_GOTRUE_URL ?? 'http://localhost:9999';
const APP_ORIGIN = process.env.NEXT_PUBLIC_APP_ORIGIN ?? 'http://localhost:3000';

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      router.push('/');
    } catch {
      setError('Email or password is incorrect.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="font-eyebrow text-xs uppercase tracking-wide text-[var(--mute)]">
        GenQL // Sign in
      </h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
      <div className="flex flex-col gap-2">
        <a
          className="text-center text-sm text-[var(--mute)] underline"
          href={`${GOTRUE_URL}/authorize?provider=google&redirect_to=${encodeURIComponent(`${APP_ORIGIN}/callback`)}`}
        >
          Continue with Google
        </a>
        <a
          className="text-center text-sm text-[var(--mute)] underline"
          href={`${GOTRUE_URL}/authorize?provider=github&redirect_to=${encodeURIComponent(`${APP_ORIGIN}/callback`)}`}
        >
          Continue with GitHub
        </a>
      </div>
      <p className="text-center text-sm text-[var(--mute)]">
        No account? <a className="underline" href="/signup">Sign up</a>
      </p>
    </main>
  );
}
