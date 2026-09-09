'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '@/lib/auth';
import { listThreads } from '@/lib/api-client';
import type { ThreadSummary } from '@/lib/types';

interface ThreadListContextValue {
  threads: ThreadSummary[];
  loading: boolean;
  refresh: () => Promise<void>;
}

const ThreadListContext = createContext<ThreadListContextValue | null>(null);

export function ThreadListProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const { session } = useAuth();
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      setThreads(await listThreads(session.accessToken));
    } catch {
      // Keep whatever list we already have rather than blanking it on a
      // transient failure.
    }
  }, [session]);

  useEffect(() => {
    // No session yet (still resolving, or signed out on the way to /login) —
    // nothing to fetch. The provider only stays mounted while ChatLayout does,
    // and that redirects away as soon as it's clear there is no session, so
    // there is no lingering "stuck loading" state to reset here.
    if (!session) return;
    let cancelled = false;
    listThreads(session.accessToken)
      .then((list) => {
        if (!cancelled) setThreads(list);
      })
      .catch(() => {
        if (!cancelled) setThreads([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  return (
    <ThreadListContext.Provider value={{ threads, loading, refresh }}>
      {children}
    </ThreadListContext.Provider>
  );
}

export function useThreadList(): ThreadListContextValue {
  const ctx = useContext(ThreadListContext);
  if (!ctx) throw new Error('useThreadList must be used within ThreadListProvider');
  return ctx;
}
