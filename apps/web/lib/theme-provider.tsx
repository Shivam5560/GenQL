'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '@/lib/auth';
import { getProfile } from '@/lib/api-client';
import { applyTheme, readStoredTheme, storeTheme } from '@/lib/theme';
import type { ThemePreference } from '@/lib/types';

interface ThemeContextValue {
  preference: ThemePreference;
  /** Applies the preference to <html> (both systems) and caches it locally. */
  setPreference: (next: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const { session } = useAuth();
  // Seeded from the same cache the boot script read, so the first effect below
  // re-applies what is already on <html> rather than flipping it.
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredTheme);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    storeTheme(next);
  }, []);

  useEffect(() => {
    applyTheme(preference);
  }, [preference]);

  // While on 'system', follow the OS switching under us — tokens.css's media
  // query does, and `.dark` has to move with it.
  useEffect(() => {
    if (preference !== 'system') return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => applyTheme('system');
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [preference]);

  // The stored value is only a head start; once the profile loads it wins.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    getProfile(session.accessToken)
      .then((profile) => {
        if (!cancelled) setPreference(profile.theme_preference);
      })
      .catch(() => {
        // Profile unreachable — keep the cached/system theme rather than flipping
      });
    return () => {
      cancelled = true;
    };
  }, [session, setPreference]);

  return (
    <ThemeContext.Provider value={{ preference, setPreference }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
