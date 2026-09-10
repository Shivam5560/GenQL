'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ThreadSummary } from '@/lib/types';

/**
 * Threads, a page at a time, in a region that never changes height.
 *
 * Rendering all of them is what made the sidebar grow until the whole thing
 * scrolled — datasources, threads, the nav and the account row sliding away
 * together, so "New thread" and "Settings" were both somewhere off-screen.
 * A fixed page keeps the list's height constant no matter how many threads
 * exist, which is what lets everything around it stay pinned.
 *
 * Paged client-side, deliberately. `GET /v1/threads` returns the caller's
 * whole list already ordered by last activity, and it arrives in one request
 * the sidebar makes once per session — so paging here costs nothing and adds
 * no round trip. If that list ever grows to the point where fetching it whole
 * is the problem, the fix is a limit/offset on the endpoint, and this
 * component's props do not have to change for it.
 */
const PER_PAGE = 8;

export function ThreadList({ threads }: { threads: ThreadSummary[] }) {
  const pathname = usePathname();
  const [requestedPage, setPage] = useState(0);

  const pageCount = Math.max(Math.ceil(threads.length / PER_PAGE), 1);
  // Clamped on the way out rather than corrected in state. A thread deleted,
  // or a first turn recorded, can shorten the list under a reader sitting on
  // the last page; deriving the page means that reader sees the last page
  // that exists, and is returned to where they were if the list grows back.
  const page = Math.min(requestedPage, pageCount - 1);

  const start = page * PER_PAGE;
  const visible = threads.slice(start, start + PER_PAGE);

  return (
    <div className="flex min-h-0 flex-1 flex-col border-t border-[var(--line)]">
      <div className="flex items-center justify-between gap-2 px-4.5 pb-1 pt-2.5">
        <p className="text-[0.72rem] text-[var(--mute)]">
          Threads
        </p>
        {threads.length > 0 && (
          <span className="font-mono text-[0.6rem] tabular-nums text-[var(--mute)]">
            {threads.length === 0 ? 0 : start + 1}–{Math.min(start + PER_PAGE, threads.length)} of{' '}
            {threads.length}
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {visible.map((thread) => {
          const href = `/thread/${thread.thread_id}`;
          const active = pathname === href;
          return (
            <Link
              key={thread.thread_id}
              href={href}
              title={thread.title}
              className={`block border-l-2 px-4.5 py-1.5 text-[0.82rem] ${
                active
                  ? 'border-l-[var(--brand)] bg-[var(--panel-2)] font-semibold text-[var(--ink)]'
                  : 'border-l-transparent text-[var(--mute)]'
              }`}
            >
              {/* One line, ellipsised. A three-line title pushed the rest of
                  the page down and made the list's height depend on how long
                  someone's question was. */}
              <span className="block truncate">{thread.title}</span>
            </Link>
          );
        })}
        {threads.length === 0 && (
          <p className="px-4.5 py-2 text-[0.82rem] text-[var(--mute)]">No threads yet.</p>
        )}
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-between gap-2 border-t border-[var(--line)] px-4.5 py-1.5">
          <button
            type="button"
            onClick={() => setPage(Math.max(page - 1, 0))}
            disabled={page === 0}
            className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[0.7rem] text-[var(--mute)] disabled:opacity-40"
          >
            ‹ Prev
          </button>
          <span className="font-mono text-[0.62rem] tabular-nums text-[var(--mute)]">
            {page + 1}/{pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage(Math.min(page + 1, pageCount - 1))}
            disabled={page >= pageCount - 1}
            className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[0.7rem] text-[var(--mute)] disabled:opacity-40"
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  );
}
