'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listDatasources, listThreads } from '@/lib/api-client';
import { DatasourceCard } from '@/components/sidebar/datasource-card';
import { ThreadList } from '@/components/sidebar/thread-list';
import type { Datasource, ThreadSummary } from '@/lib/types';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();
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

  return (
    <div className="grid min-h-screen grid-cols-[264px_1fr]">
      <aside className="flex flex-col border-r border-[var(--line)]">
        <div className="border-b border-[var(--line)] px-5 py-4 text-base font-bold uppercase tracking-wide">
          Gen<span className="text-[var(--accent)]">QL</span>
        </div>
        <div className="border-b border-[var(--line)] px-4.5 py-4">
          {datasources[0] && <DatasourceCard datasource={datasources[0]} />}
        </div>
        <ThreadList threads={threads} />
        <div className="font-eyebrow mt-auto border-t border-[var(--line)] px-4.5 py-3.5 text-[0.66rem] text-[var(--mute)]">
          {session.user.email}
        </div>
      </aside>
      <div className="flex min-h-screen flex-col">{children}</div>
    </div>
  );
}
