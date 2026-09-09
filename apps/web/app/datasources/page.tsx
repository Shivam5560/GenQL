'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { listDatasources } from '@/lib/api-client';
import type { Datasource } from '@/lib/types';

export default function DatasourcesPage() {
  const { session } = useAuth();
  const [datasources, setDatasources] = useState<Datasource[] | null>(null);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken).then(setDatasources);
  }, [session]);

  return (
    <main className="mx-auto max-w-[900px] px-7 py-8">
      <h1 className="font-eyebrow mb-6 text-xs uppercase tracking-wide text-[var(--mute)]">
        Datasources
      </h1>
      {datasources === null ? (
        <p className="text-sm text-[var(--mute)]">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2.5">
          {datasources.map((ds) => (
            <div
              key={ds.name}
              className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{ds.name}</span>
                <span className="font-eyebrow text-[0.66rem] uppercase text-[var(--mute)]">
                  {ds.dialect}
                </span>
              </div>
              {ds.description && (
                <p className="mt-1 text-sm text-[var(--mute)]">{ds.description}</p>
              )}
            </div>
          ))}
          {datasources.length === 0 && (
            <p className="text-sm text-[var(--mute)]">No datasources registered.</p>
          )}
        </div>
      )}
    </main>
  );
}
