'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

export function ExecuteButton({ onReveal }: { onReveal: () => void }) {
  const [running, setRunning] = useState(false);

  function handleClick() {
    setRunning(true);
    setTimeout(() => {
      onReveal();
      setRunning(false);
    }, 400);
  }

  return (
    <Button
      onClick={handleClick}
      disabled={running}
      className="shrink-0 bg-[var(--brand)] font-sans text-sm font-semibold text-[var(--brand-ink)] hover:brightness-105"
    >
      {running ? 'Running…' : 'Run query'}
    </Button>
  );
}
