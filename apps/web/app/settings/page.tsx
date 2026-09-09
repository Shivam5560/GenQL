'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { getProfile, updateTheme } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import type { ThemePreference } from '@/lib/types';

const THEMES: ThemePreference[] = ['light', 'dark', 'system'];

export default function SettingsPage() {
  const { session, logout } = useAuth();
  const [theme, setTheme] = useState<ThemePreference | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!session) return;
    getProfile(session.accessToken).then((profile) => setTheme(profile.theme_preference));
  }, [session]);

  async function onChangeTheme(next: ThemePreference) {
    if (!session) return;
    setSaving(true);
    try {
      const profile = await updateTheme(session.accessToken, next);
      setTheme(profile.theme_preference);
      document.documentElement.setAttribute(
        'data-theme',
        profile.theme_preference === 'system' ? '' : profile.theme_preference,
      );
    } finally {
      setSaving(false);
    }
  }

  if (!session) return null;

  return (
    <main className="mx-auto max-w-[560px] px-7 py-8">
      <h1 className="font-eyebrow mb-6 text-xs uppercase tracking-wide text-[var(--mute)]">
        Settings
      </h1>
      <div className="flex flex-col gap-6">
        <div>
          <p className="mb-1 text-sm font-semibold">Email</p>
          <p className="text-sm text-[var(--mute)]">{session.user.email}</p>
        </div>
        <div>
          <p className="mb-2 text-sm font-semibold">Theme</p>
          <div className="flex gap-2">
            {THEMES.map((option) => (
              <button
                key={option}
                disabled={saving}
                onClick={() => onChangeTheme(option)}
                className={`font-eyebrow rounded border px-3 py-1.5 text-[0.7rem] uppercase tracking-wide ${
                  theme === option
                    ? 'border-[var(--accent)] bg-[var(--panel-2)] text-[var(--ink)]'
                    : 'border-[var(--line)] text-[var(--mute)]'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <Button variant="outline" onClick={() => logout()}>
          Sign out
        </Button>
      </div>
    </main>
  );
}
