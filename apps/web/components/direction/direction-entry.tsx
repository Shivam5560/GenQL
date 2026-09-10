'use client';

import { useState } from 'react';
import { DirectionHeader } from './direction-header';
import { DirectionHero } from './direction-hero';
import { DirectionTrail } from './direction-trail';
import { DirectionWorkspace } from './direction-workspace';
import { DirectionGates } from './direction-gates';
import { DirectionFooter } from './direction-footer';
import { AuthPanel, type AuthMode } from './auth-panel';

/**
 * GenQL's entry screen: the "GenQL Direction" marketing composition —
 * hero, trail, workspace showcase, gates, footer — with the same sign-in
 * panel opened from the header, the hero CTAs, and the footer.
 *
 * Both `/login` and `/signup` render this; the route decides which mode the
 * panel opens in, matching the previous Keystone entry's contract.
 */
export function DirectionEntry({
  initialMode,
  openOnMount = false,
}: {
  initialMode: AuthMode;
  openOnMount?: boolean;
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [open, setOpen] = useState(openOnMount);

  function openAuth(next: AuthMode) {
    setMode(next);
    setOpen(true);
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <DirectionHeader onAuth={openAuth} />
      <main>
        <DirectionHero />
        <DirectionTrail />
        <DirectionWorkspace />
        <DirectionGates />
      </main>
      <DirectionFooter />

      {open && <AuthPanel mode={mode} onModeChange={setMode} onClose={() => setOpen(false)} />}
    </div>
  );
}
