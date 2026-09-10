'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { submitFeedback } from '@/lib/api-client';

export function FeedbackRow({ accessToken, threadId }: { accessToken: string; threadId: string }) {
  const [picked, setPicked] = useState<'good' | 'bad' | null>(null);

  async function pick(rating: 'good' | 'bad') {
    setPicked(rating);
    await submitFeedback(accessToken, threadId, { rating }).catch(() => {
      setPicked(null);
      toast.error('Could not send feedback — try again.');
    });
  }

  const baseClass = 'rounded border px-2.5 py-1 font-eyebrow text-[0.62rem] uppercase tracking-[0.1em]';
  const idleClass = 'border-[var(--line)] bg-[var(--panel)] text-[var(--mute)]';
  const pickedClass = 'border-[var(--ok)] bg-[var(--ok-soft)] text-[var(--ok)]';

  return (
    <div className="flex items-center gap-2">
      <span className="font-eyebrow text-[0.62rem] uppercase tracking-[0.1em] text-[var(--mute)]">
        Was this right?
      </span>
      <button
        type="button"
        className={`${baseClass} ${picked === 'good' ? pickedClass : idleClass}`}
        onClick={() => pick('good')}
      >
        Yes
      </button>
      <button
        type="button"
        className={`${baseClass} ${picked === 'bad' ? pickedClass : idleClass}`}
        onClick={() => pick('bad')}
      >
        Not quite
      </button>
    </div>
  );
}
