'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme-provider';
import { updateTheme } from '@/lib/api-client';
import type { ThemePreference } from '@/lib/types';

/**
 * Light / dark / system, in the sidebar where it is reachable from any screen.
 *
 * It was only on the settings page — two navigations away from the thread you
 * are reading, which is the one moment you actually notice the theme is wrong.
 *
 * The switch is applied locally first and saved afterwards. `setPreference`
 * writes to <html> and to localStorage synchronously, so the theme changes on
 * the click rather than after a round trip; a failed save is reported but
 * never reverts what is on screen, because the local preference is what the
 * next page load reads anyway.
 */
const OPTIONS: { value: ThemePreference; label: string; glyph: string }[] = [
  { value: 'light', label: 'Light', glyph: '☀' },
  { value: 'dark', label: 'Dark', glyph: '☾' },
  { value: 'system', label: 'System', glyph: '⌥' },
];

export function ThemeToggle() {
  const { session } = useAuth();
  const { preference, setPreference } = useTheme();
  const [saving, setSaving] = useState(false);

  async function choose(next: ThemePreference) {
    if (next === preference) return;
    setPreference(next);
    if (!session) return;
    setSaving(true);
    try {
      await updateTheme(session.accessToken, next);
    } catch {
      toast.error('Theme changed here, but could not be saved to your profile.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex items-center gap-0.5 rounded-md border border-[var(--line)] p-0.5"
    >
      {OPTIONS.map(({ value, label, glyph }) => (
        <button
          key={value}
          type="button"
          disabled={saving}
          onClick={() => void choose(value)}
          aria-pressed={preference === value}
          title={label}
          className={`rounded px-1.5 py-0.5 text-[0.7rem] leading-none ${
            preference === value
              ? 'bg-[var(--panel-2)] text-[var(--ink)]'
              : 'text-[var(--mute)] hover:text-[var(--ink)]'
          }`}
        >
          <span aria-hidden>{glyph}</span>
          <span className="sr-only">{label}</span>
        </button>
      ))}
    </div>
  );
}
