'use client';

import { useCallback, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { streamDatasourceEvents } from '@/lib/api-client';
import { DatasourceProvider, useDatasources } from '@/lib/datasource-provider';
import { ThreadListProvider, useThreadList } from '@/lib/thread-list-provider';
import { DatasourceList } from '@/components/sidebar/datasource-list';
import { ThreadList } from '@/components/sidebar/thread-list';

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

function SidebarLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className={`block border-l-2 px-4.5 py-2 text-sm ${
        active
          ? 'border-l-[var(--brand)] bg-[var(--panel-2)] font-semibold text-[var(--ink)]'
          : 'border-l-transparent text-[var(--mute)]'
      }`}
    >
      {label}
    </Link>
  );
}

function ChatShell({ children }: { children: React.ReactNode }) {
  const { session, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { threads, loading: threadsLoading } = useThreadList();
  const { refresh: refreshDatasources } = useDatasources();
  const onDatasourceChange = useCallback(() => void refreshDatasources(), [refreshDatasources]);

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
        <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-5 py-4">
          <Link href="/" className="text-base font-bold uppercase tracking-wide">
            Gen<span className="text-[var(--brand)]">QL</span>
          </Link>
        </div>
        {/* The way back to the composer, on screen from every thread. Without
            it, opening a thread was a one-way trip: the only route to a new
            question was the browser's back button or editing the URL. */}
        <div className="px-4.5 pb-3 pt-3.5">
          <Link
            href="/"
            className={`flex items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-semibold ${
              pathname === '/'
                ? 'border-[var(--brand)] bg-[var(--panel-2)] text-[var(--ink)]'
                : 'border-[var(--line)] text-[var(--ink)]'
            }`}
          >
            <span aria-hidden>+</span> New thread
          </Link>
        </div>
        <DatasourceList />
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
          <SidebarLink
            href="/datasources"
            label="Datasources"
            active={pathname === '/datasources'}
          />
          <SidebarLink href="/settings" label="Settings" active={pathname === '/settings'} />
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
    <DatasourceProvider>
      <ThreadListProvider>
        <ChatShell>{children}</ChatShell>
      </ThreadListProvider>
    </DatasourceProvider>
  );
}
