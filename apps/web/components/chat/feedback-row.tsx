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

  const baseClass = 'font-eyebrow rounded border px-2.5 py-1 text-[0.66rem] uppercase tracking-wide';
  const idleClass = 'border-[var(--line)] bg-[var(--panel)] text-[var(--mute)]';
  const pickedClass = 'border-[var(--ok)] bg-[var(--ok-soft)] text-[var(--ok)]';

  return (
    <div className="flex gap-1.5">
      <button className={`${baseClass} ${picked === 'good' ? pickedClass : idleClass}`} onClick={() => pick('good')}>
        Helpful
      </button>
      <button className={`${baseClass} ${picked === 'bad' ? pickedClass : idleClass}`} onClick={() => pick('bad')}>
        Needs work
      </button>
      <button className={`${baseClass} ${idleClass}`} disabled>
        Suggest SQL
      </button>
    </div>
  );
}
