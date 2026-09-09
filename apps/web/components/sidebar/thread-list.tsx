'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ThreadSummary } from '@/lib/types';

export function ThreadList({ threads }: { threads: ThreadSummary[] }) {
  const pathname = usePathname();

  return (
    <div className="py-1.5">
      <p className="font-eyebrow px-4.5 pb-1 pt-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
        Threads
      </p>
      {threads.map((thread) => {
        const href = `/thread/${thread.thread_id}`;
        const active = pathname === href;
        return (
          <Link
            key={thread.thread_id}
            href={href}
            className={`block border-l-2 px-4.5 py-2 text-sm ${
              active
                ? 'border-l-[var(--brand)] bg-[var(--panel-2)] font-semibold text-[var(--ink)]'
                : 'border-l-transparent text-[var(--mute)]'
            }`}
          >
            {thread.title}
          </Link>
        );
      })}
      {threads.length === 0 && (
        <p className="px-4.5 py-2 text-sm text-[var(--mute)]">No threads yet.</p>
      )}
    </div>
  );
}
