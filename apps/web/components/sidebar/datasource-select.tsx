'use client';

import Link from 'next/link';
import { useDatasources } from '@/lib/datasource-provider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

/**
 * Which warehouse questions go to, as one row that never changes height.
 *
 * This replaces a stack of cards — one per datasource — which is what made the
 * sidebar grow past the viewport and start scrolling as a whole. A dropdown is
 * a fixed row whatever the list holds, and the popup does its own scrolling,
 * so ten warehouses cost exactly as much sidebar as one.
 *
 * The endpoint sits under the trigger rather than inside it: a person needs to
 * see what the selected datasource points at without opening anything, and
 * `host:port/database` does not fit on the same line as the name at this
 * width.
 */
export function DatasourceSelect() {
  const { datasources, selected, select, loading } = useDatasources();

  if (loading) {
    return (
      <div className="px-4.5 py-3">
        <div className="mb-2 h-[0.6rem] w-16 animate-pulse rounded bg-[var(--panel-2)]" />
        <div className="h-8 animate-pulse rounded-md bg-[var(--panel-2)]" />
      </div>
    );
  }

  return (
    <div className="px-4.5 py-3">
      <p className="font-eyebrow mb-1.5 text-[0.6rem] uppercase tracking-wide text-[var(--mute)]">
        Datasource
      </p>
      {datasources.length === 0 ? (
        <Link
          href="/datasources"
          className="block rounded-md border border-dashed border-[var(--line)] px-2.5 py-1.5 text-[0.8rem] text-[var(--mute)]"
        >
          Connect a warehouse →
        </Link>
      ) : (
        <>
          <Select value={selected?.name ?? ''} onValueChange={(next) => next && select(next)}>
            <SelectTrigger className="w-full" aria-label="Datasource">
              <SelectValue placeholder="Choose one" />
            </SelectTrigger>
            <SelectContent>
              {datasources.map((ds) => (
                <SelectItem key={ds.name} value={ds.name}>
                  {ds.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selected && (
            <p className="mt-1 truncate font-mono text-[0.66rem] text-[var(--mute)]">
              {selected.endpoint ?? selected.dialect}
            </p>
          )}
        </>
      )}
    </div>
  );
}
