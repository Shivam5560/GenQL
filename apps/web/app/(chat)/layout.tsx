'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listDatasources, listThreads } from '@/lib/api-client';
import { DatasourceCard } from '@/components/sidebar/datasource-card';
import { ThreadList } from '@/components/sidebar/thread-list';
import type { Datasource, ThreadSummary } from '@/lib/types';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { session, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);

  useEffect(() => {
    if (!loading && !session) router.push('/login');
  }, [loading, session, router]);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken).then(setDatasources).catch(() => setDatasources([]));
    listThreads(session.accessToken).then(setThreads).catch(() => setThreads([]));
  }, [session]);

  if (loading || !session) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--mute)]">Loading…</p>
      </main>
    );
  }

  async function onSignOut() {
    await logout();
    router.push('/login');
  }

  return (
    <div className="grid min-h-screen grid-cols-[264px_1fr]">
      <aside className="flex flex-col border-r border-[var(--line)]">
        <div className="border-b border-[var(--line)] px-5 py-4 text-base font-bold uppercase tracking-wide">
          Gen<span className="text-[var(--brand)]">QL</span>
        </div>
        <div className="border-b border-[var(--line)] px-4.5 py-4">
          {datasources[0] && <DatasourceCard datasource={datasources[0]} />}
        </div>
        <ThreadList threads={threads} />
        <nav className="mt-auto flex flex-col border-t border-[var(--line)] py-1.5">
          <Link
            href="/datasources"
            className={`block border-l-2 px-4.5 py-2 text-sm ${
              pathname === '/datasources'
                ? 'border-l-[var(--brand)] bg-[var(--panel-2)] font-semibold text-[var(--ink)]'
                : 'border-l-transparent text-[var(--mute)]'
            }`}
          >
            Datasources
          </Link>
          <Link
            href="/settings"
            className={`block border-l-2 px-4.5 py-2 text-sm ${
              pathname === '/settings'
                ? 'border-l-[var(--brand)] bg-[var(--panel-2)] font-semibold text-[var(--ink)]'
                : 'border-l-transparent text-[var(--mute)]'
            }`}
          >
            Settings
          </Link>
        </nav>
        <div className="font-eyebrow flex items-center justify-between gap-2 border-t border-[var(--line)] px-4.5 py-3.5 text-[0.66rem] text-[var(--mute)]">
          <span className="truncate">{session.user.email}</span>
          <button
            type="button"
            onClick={onSignOut}
            className="font-eyebrow shrink-0 rounded border border-[var(--line)] px-2 py-1 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]"
          >
            Sign out
          </button>
        </div>
      </aside>
      <div className="flex min-h-screen flex-col">{children}</div>
    </div>
  );
}
