'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { listDatasources, streamDatasourceEvents } from '@/lib/api-client';
import { ThreadListProvider, useThreadList } from '@/lib/thread-list-provider';
import { DatasourceCard } from '@/components/sidebar/datasource-card';
import { ThreadList } from '@/components/sidebar/thread-list';
import type { Datasource } from '@/lib/types';

function DatasourceSection({
  session,
  epoch,
}: {
  session: { accessToken: string };
  /** Bumped when ingestion finishes, so a warehouse that just became
      queryable appears here without a reload. */
  epoch: number;
}) {
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [loadingDatasources, setLoadingDatasources] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listDatasources(session.accessToken)
      .then((list) => {
        if (!cancelled) setDatasources(list);
      })
      .catch(() => {
        if (!cancelled) setDatasources([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingDatasources(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, epoch]);

  if (loadingDatasources) {
    return (
      <div className="border-b border-[var(--line)] px-4.5 py-4">
        <div className="mb-2.5 h-[0.66rem] w-20 animate-pulse rounded bg-[var(--panel-2)]" />
        <div className="h-[3.25rem] animate-pulse rounded-md bg-[var(--panel-2)]" />
      </div>
    );
  }

  if (!datasources[0]) return null;

  return (
    <div className="border-b border-[var(--line)] px-4.5 py-4">
      <DatasourceCard datasource={datasources[0]} />
    </div>
  );
}

/**
 * Holds the app-wide datasource stream open for the life of the session.
 *
 * Ingesting a warehouse takes minutes, so whoever submitted it has navigated
 * somewhere else long before it finishes. This is what lets "your warehouse is
 * ready" find them there. It lives in the layout, not on the datasources page,
 * for exactly that reason.
 */
function useDatasourceNotifications(accessToken: string | undefined, onChange: () => void) {
  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void streamDatasourceEvents(
      accessToken,
      {
        onReady: ({ datasource }) => {
          toast.success(`${datasource} is ready to query.`);
          onChange();
        },
        onFailed: ({ datasource, error_step }) => {
          toast.error(
            error_step
              ? `${datasource} could not be prepared — ${error_step.replace(/_/g, ' ')} failed.`
              : `${datasource} could not be prepared.`,
          );
          onChange();
        },
      },
      controller.signal,
    );
    return () => controller.abort();
  }, [accessToken, onChange]);
}

function ChatShell({ children }: { children: React.ReactNode }) {
  const { session, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { threads, loading: threadsLoading } = useThreadList();
  const [datasourceEpoch, setDatasourceEpoch] = useState(0);
  const onDatasourceChange = useCallback(() => setDatasourceEpoch((e) => e + 1), []);

  useDatasourceNotifications(session?.accessToken, onDatasourceChange);

  useEffect(() => {
    if (!loading && !session) router.push('/login');
  }, [loading, session, router]);

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
    <div className="grid h-screen grid-cols-[264px_1fr] overflow-hidden">
      {/* The sidebar leads the one page-load sequence; the hero's headline,
          supporting line and composer follow it on staggered delays. */}
      <aside className="gq-slide-in flex min-h-0 flex-col overflow-y-auto border-r border-[var(--line)]">
        <div className="border-b border-[var(--line)] px-5 py-4 text-base font-bold uppercase tracking-wide">
          Gen<span className="text-[var(--brand)]">QL</span>
        </div>
        <DatasourceSection session={session} epoch={datasourceEpoch} />
        {threadsLoading ? (
          <div className="py-1.5">
            <p className="font-eyebrow px-4.5 pb-1 pt-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
              Threads
            </p>
            <div className="flex flex-col gap-2 px-4.5 py-1">
              <div className="h-4 w-3/4 animate-pulse rounded bg-[var(--panel-2)]" />
              <div className="h-4 w-1/2 animate-pulse rounded bg-[var(--panel-2)]" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--panel-2)]" />
            </div>
          </div>
        ) : (
          <ThreadList threads={threads} />
        )}
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
      <div className="flex min-h-0 flex-col">{children}</div>
    </div>
  );
}

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <ThreadListProvider>
      <ChatShell>{children}</ChatShell>
    </ThreadListProvider>
  );
}
