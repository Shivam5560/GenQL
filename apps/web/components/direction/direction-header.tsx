'use client';

import { ThemeToggle } from '@/components/sidebar/theme-toggle';
import type { AuthMode } from './auth-panel';

/**
 * Sticky header for the entry screen: brand, section nav, theme toggle, and
 * the two doors in — everything the composition needs before a visitor has
 * decided whether to sign in or read the method first.
 */
export function DirectionHeader({ onAuth }: { onAuth: (mode: AuthMode) => void }) {
  return (
    <header className="sticky top-0 z-50 flex items-center justify-between gap-5 border-b border-[var(--line)] bg-[color-mix(in_oklab,var(--bg)_78%,transparent)] px-6 py-4 backdrop-blur-xl md:px-10">
      <div className="flex min-w-0 items-baseline gap-3">
        <a href="#" className="font-eyebrow text-[15px] font-medium uppercase tracking-[0.14em]">
          Gen<span className="text-[var(--brand)]">QL</span>
        </a>
        <span className="hidden font-eyebrow text-[9.5px] uppercase tracking-[0.18em] text-[var(--mute)] sm:inline">
          Text-to-SQL, under audit
        </span>
      </div>
      <div className="flex items-center gap-4 md:gap-7">
        <nav className="hidden items-center gap-6 font-eyebrow text-[10.5px] uppercase tracking-[0.14em] text-[var(--mute)] md:flex">
          <a href="#trail" className="hover:text-[var(--ink)]">
            Trail
          </a>
          <a href="#workspace" className="hover:text-[var(--ink)]">
            Workspace
          </a>
          <a
            href="https://github.com/Shivam5560/GenQL"
            className="hover:text-[var(--ink)]"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </nav>
        <ThemeToggle />
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => onAuth('login')}
            className="font-eyebrow text-[10.5px] uppercase tracking-[0.14em] text-[var(--mute)] hover:text-[var(--ink)]"
          >
            Log in
          </button>
          <button
            type="button"
            onClick={() => onAuth('register')}
            className="whitespace-nowrap bg-[var(--brand)] px-3.5 py-2 font-eyebrow text-[10.5px] uppercase tracking-[0.12em] text-[var(--brand-ink)]"
          >
            Request access
          </button>
        </div>
      </div>
    </header>
  );
}
