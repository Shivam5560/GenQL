import type { ThemePreference } from './types';

/**
 * Where the last known preference is cached so the inline boot script (see
 * `components/theme-script.tsx`) can paint the right theme before React runs.
 * The server profile stays the source of truth; this is only a head start.
 */
export const THEME_STORAGE_KEY = 'genql-theme';

export type ThemeMode = 'light' | 'dark';

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system';
}

/**
 * The mode a preference actually resolves to. `system` follows
 * `prefers-color-scheme`, matching the media query in `styles/tokens.css`, so
 * the class-based and attribute-based systems can never disagree.
 */
export function resolveMode(preference: ThemePreference): ThemeMode {
  if (preference !== 'system') return preference;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/**
 * Drives both theme systems from one preference:
 *   - `data-theme` on <html> selects the Swiss tokens in `styles/tokens.css`
 *   - `.dark` on <html> selects Tailwind's `dark:` variant, which every shadcn
 *     primitive in `components/ui/` relies on
 * They are always written together — a `.dark` that lags `data-theme` is what
 * left shadcn primitives rendering light borders on a dark page.
 */
export function applyTheme(preference: ThemePreference): void {
  const root = document.documentElement;
  if (preference === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', preference);
  root.classList.toggle('dark', resolveMode(preference) === 'dark');
}

export function readStoredTheme(): ThemePreference {
  if (typeof window === 'undefined') return 'system';
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : 'system';
  } catch {
    return 'system'; // localStorage unavailable (private mode) — fall back to system
  }
}

export function storeTheme(preference: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // localStorage unavailable — the profile fetch still restores the choice
  }
}
