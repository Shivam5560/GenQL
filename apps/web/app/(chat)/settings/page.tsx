'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme-provider';
import { updateTheme } from '@/lib/api-client';
import type { ThemePreference } from '@/lib/types';

const THEMES: ThemePreference[] = ['light', 'dark', 'system'];
const GENERIC_ERROR = 'Something went wrong — try again.';

export default function SettingsPage() {
  const { session } = useAuth();
  // The provider already loaded the saved preference and owns applying it to
  // <html> — both `data-theme` and `.dark` — so this page only has to save.
  const { preference, setPreference } = useTheme();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onChangeTheme(next: ThemePreference) {
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      const profile = await updateTheme(session.accessToken, next);
      setPreference(profile.theme_preference);
    } catch {
      setError(GENERIC_ERROR);
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
                  preference === option
                    ? 'border-[var(--brand)] bg-[var(--panel-2)] text-[var(--ink)]'
                    : 'border-[var(--line)] text-[var(--mute)]'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </main>
  );
}
