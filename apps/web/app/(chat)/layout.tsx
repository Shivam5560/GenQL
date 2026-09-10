'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { streamDatasourceEvents } from '@/lib/api-client';
import { DatasourceProvider, useDatasources } from '@/lib/datasource-provider';
import { ThreadListProvider, useThreadList } from '@/lib/thread-list-provider';
import { DatasourceSelect } from '@/components/sidebar/datasource-select';
import { ThemeToggle } from '@/components/sidebar/theme-toggle';
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
  // Below `md` the sidebar is an off-canvas drawer rather than a fixed
  // column — a 264px rail alongside content leaves too little width to be
  // usable on a phone. Any navigation closes it, so picking a thread from
  // the drawer always lands on that thread's screen, not on the drawer.
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Reset during render on route change rather than in an effect — the
  // recommended way to adjust state from a prop-like value without an extra
  // render pass. See https://react.dev/learn/you-might-not-need-an-effect.
  const [lastPathname, setLastPathname] = useState(pathname);
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setSidebarOpen(false);
  }

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
    <div className="relative grid h-screen grid-cols-1 overflow-hidden md:grid-cols-[264px_1fr]">
      {/* A tap-to-close scrim behind the drawer on narrow screens; absent —
          and untouchable — once the sidebar is a static column at `md`. */}
      {sidebarOpen && (
        <div
          aria-hidden
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
        />
      )}
      {/* `overflow-hidden`, not `overflow-y-auto`: the sidebar is exactly the
          height of the viewport and nothing in it moves. Everything here is a
          fixed-height row except the thread list, which is the one region
          allowed to flex and to scroll — so the brand, New thread, the
          datasource picker, the nav and the account row are always where they
          were, however many threads or warehouses exist.

          The sidebar also leads the one page-load sequence; the hero's
          headline, supporting line and composer follow on staggered delays.
          Below `md` it is fixed off-canvas, sliding in over the content
          instead of sharing the row with it. */}
      <aside
        className={`gq-slide-in fixed inset-y-0 left-0 z-40 flex w-[264px] min-h-0 flex-col overflow-hidden border-r border-[var(--line)] bg-[var(--bg)] transition-transform duration-200 ease-out md:static md:z-auto md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--line)] px-4.5 py-3.5">
          <Link href="/" className="text-base font-bold uppercase tracking-wide">
            Gen<span className="text-[var(--brand)]">QL</span>
          </Link>
          <ThemeToggle />
        </div>
        {/* The way back to the composer, on screen from every thread. Without
            it, opening a thread was a one-way trip: the only route to a new
            question was the browser's back button or editing the URL. */}
        <div className="shrink-0 px-4.5 pb-2.5 pt-3">
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
        <div className="shrink-0">
          <DatasourceSelect />
        </div>
        {threadsLoading ? (
          <div className="min-h-0 flex-1 border-t border-[var(--line)] py-1.5">
            <p className="px-4.5 pb-1 pt-1 text-[0.72rem] text-[var(--mute)]">
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
        <nav className="flex shrink-0 flex-col border-t border-[var(--line)] py-1">
          <SidebarLink
            href="/datasources"
            label="Datasources"
            active={pathname === '/datasources'}
          />
          <SidebarLink href="/settings" label="Settings" active={pathname === '/settings'} />
        </nav>
        <div className="flex shrink-0 items-center justify-between gap-2 border-t border-[var(--line)] px-4.5 py-3 text-[0.74rem] text-[var(--mute)]">
          <span className="truncate">{session.user.email}</span>
          <button
            type="button"
            onClick={onSignOut}
            className="shrink-0 rounded border border-[var(--line)] px-2 py-1 text-[0.72rem] text-[var(--mute)]"
          >
            Sign out
          </button>
        </div>
      </aside>
      <div className="flex min-h-0 flex-col">
        {/* Own row rather than overlaying the page's own header: every child
            route (thread, composer, datasources, settings) draws its own
            header content flush to the left edge, so a floating button there
            would sit on top of a title instead of beside it. */}
        <div className="flex shrink-0 items-center gap-3 border-b border-[var(--line)] px-4.5 py-2.5 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--line)] text-[var(--ink)]"
          >
            <span aria-hidden className="text-base leading-none">
              ☰
            </span>
          </button>
          <span className="text-sm font-bold uppercase tracking-wide">
            Gen<span className="text-[var(--brand)]">QL</span>
          </span>
        </div>
        {children}
      </div>
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
