'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useAuth } from '@/lib/auth';
import { listDatasources } from '@/lib/api-client';
import type { Datasource } from '@/lib/types';

/**
 * Which warehouse the next question goes to, held for the whole session.
 *
 * Before this, the list was fetched twice — once by the sidebar, which showed
 * `datasources[0]` and nothing else, and once by the composer, which owned the
 * only picker in the app. Three connected warehouses were therefore two
 * invisible ones, and a thread opened from the sidebar had no way to say which
 * of them it was asking. One provider, one list, one selection.
 *
 * The choice is remembered in `localStorage` rather than on the profile: it is
 * a per-browser convenience, not an account setting, and a round trip to save
 * it would make clicking a datasource feel like a mutation. A remembered name
 * that no longer exists (removed, renamed) falls back to the first datasource
 * rather than leaving the composer pointed at nothing.
 */
const STORAGE_KEY = 'genql.datasource';

interface DatasourceContextValue {
  datasources: Datasource[];
  selected: Datasource | null;
  select: (name: string) => void;
  loading: boolean;
  refresh: () => Promise<void>;
}

const DatasourceContext = createContext<DatasourceContextValue | null>(null);

function remembered(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private mode, or storage disabled. A forgotten preference is fine.
    return null;
  }
}

export function DatasourceProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const { session } = useAuth();
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const accessToken = session?.accessToken;

  const apply = useCallback((list: Datasource[]) => {
    setDatasources(list);
    // Only ever *fills in* a missing or stale selection. Reconciling a
    // still-valid one on every refresh would move the composer under someone
    // whose warehouse just finished ingesting.
    const has = (name: string | null) => Boolean(name && list.some((ds) => ds.name === name));
    const saved = remembered();
    setSelectedName((current) =>
      has(current) ? current : has(saved) ? saved : (list[0]?.name ?? null),
    );
  }, []);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      apply(await listDatasources(accessToken));
    } catch {
      // Keep whatever list we already have rather than blanking it on a
      // transient failure — the same call the thread list makes.
    } finally {
      setLoading(false);
    }
  }, [accessToken, apply]);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    listDatasources(accessToken)
      .then((list) => {
        if (!cancelled) apply(list);
      })
      .catch(() => {
        if (!cancelled) apply([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, apply]);

  const select = useCallback((name: string) => {
    setSelectedName(name);
    try {
      localStorage.setItem(STORAGE_KEY, name);
    } catch {
      // Same as above: not remembering is not a failure worth surfacing.
    }
  }, []);

  const value = useMemo<DatasourceContextValue>(
    () => ({
      datasources,
      selected: datasources.find((ds) => ds.name === selectedName) ?? null,
      select,
      loading,
      refresh: load,
    }),
    [datasources, selectedName, select, loading, load],
  );

  return <DatasourceContext.Provider value={value}>{children}</DatasourceContext.Provider>;
}

export function useDatasources(): DatasourceContextValue {
  const ctx = useContext(DatasourceContext);
  if (!ctx) throw new Error('useDatasources must be used within DatasourceProvider');
  return ctx;
}
