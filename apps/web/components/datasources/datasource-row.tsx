'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { Datasource } from '@/lib/types';

/**
 * One registered warehouse, with the two things you can do to it.
 *
 * Removal confirms in the row rather than in a modal: a `window.confirm` blocks
 * the page, and a dialog for a two-word question is more ceremony than the
 * question deserves. It says what removal takes with it, because it cascades —
 * the catalog, the profiles, the search index and the ingestion history all go.
 */
export function DatasourceRow({
  datasource,
  onEdit,
  onRemove,
  busy = false,
}: {
  datasource: Datasource;
  onEdit: () => void;
  onRemove: () => void;
  busy?: boolean;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold">{datasource.name}</span>
        <div className="flex items-center gap-2.5">
          {!datasource.enabled && (
            <span className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
              Off
            </span>
          )}
          <span className="font-eyebrow text-[0.66rem] uppercase text-[var(--mute)]">
            {datasource.dialect}
          </span>
          <Button type="button" variant="ghost" size="sm" onClick={onEdit} disabled={busy}>
            Edit
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setConfirming(true)}
            disabled={busy}
          >
            Remove
          </Button>
        </div>
      </div>

      {datasource.endpoint && (
        <p className="mt-1 truncate font-mono text-xs text-[var(--mute)]">{datasource.endpoint}</p>
      )}
      {datasource.description && (
        <p className="mt-1 text-sm text-[var(--mute)]">{datasource.description}</p>
      )}

      {confirming && (
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-[var(--line)] pt-3">
          <p className="text-sm text-[var(--mute)]">
            Remove {datasource.name}? Everything discovered from it goes too — catalog, profiles,
            search index, ingestion history.
          </p>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setConfirming(false);
                onRemove();
              }}
            >
              Delete it
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
