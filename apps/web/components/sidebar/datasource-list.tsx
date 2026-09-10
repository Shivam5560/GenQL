'use client';

import Link from 'next/link';
import { useDatasources } from '@/lib/datasource-provider';
import { usePointerTilt } from '@/lib/use-pointer-tilt';
import type { Datasource } from '@/lib/types';

/**
 * Every connected warehouse, with the one questions go to marked.
 *
 * This replaces a card that rendered `datasources[0]` and nothing else — so
 * with three warehouses connected, two of them were invisible from every
 * screen in the app and there was no way to point a thread at one of them
 * without going back to the composer. Selecting here is what the composer
 * reads, so the choice is made in the one place that is on screen from
 * everywhere.
 *
 * A single datasource still renders as a card rather than as a list of one:
 * offering a choice between one thing is a control that does nothing.
 */
function SelectedCard({ datasource }: { datasource: Datasource }) {
  // The one card in the app that stands for a physical thing you are pointed
  // at, so it is the one that gets depth. Four degrees, damped by the
  // transition in `.gq-tilt`; nothing attaches on touch or under reduced
  // motion.
  const { ref, tiltProps } = usePointerTilt<HTMLDivElement>(4);

  return (
    <div
      ref={ref}
      {...tiltProps}
      className="gq-tilt rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3"
    >
      <div className="truncate text-sm font-semibold">{datasource.name}</div>
      <div className="mt-0.5 truncate font-mono text-xs text-[var(--mute)]">
        {datasource.endpoint ?? datasource.dialect}
      </div>
    </div>
  );
}

function Row({
  datasource,
  active,
  onSelect,
}: {
  datasource: Datasource;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? 'true' : undefined}
      className={`flex w-full flex-col items-start rounded-md border px-3 py-2 text-left ${
        active
          ? 'border-[var(--brand)] bg-[var(--panel-2)]'
          : 'border-[var(--line)] text-[var(--mute)]'
      }`}
    >
      <span
        className={`w-full truncate text-sm ${active ? 'font-semibold text-[var(--ink)]' : ''}`}
      >
        {datasource.name}
      </span>
      <span className="w-full truncate font-mono text-[0.68rem] text-[var(--mute)]">
        {datasource.endpoint ?? datasource.dialect}
      </span>
    </button>
  );
}

export function DatasourceList() {
  const { datasources, selected, select, loading } = useDatasources();

  if (loading) {
    return (
      <div className="border-b border-[var(--line)] px-4.5 py-4">
        <div className="mb-2.5 h-[0.66rem] w-20 animate-pulse rounded bg-[var(--panel-2)]" />
        <div className="h-[3.25rem] animate-pulse rounded-md bg-[var(--panel-2)]" />
      </div>
    );
  }

  return (
    <div className="border-b border-[var(--line)] px-4.5 py-4">
      <p className="font-eyebrow mb-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
        {datasources.length > 1 ? 'Datasource — pick one' : 'Datasource'}
      </p>
      {datasources.length === 0 ? (
        <Link
          href="/datasources"
          className="block rounded-md border border-dashed border-[var(--line)] px-3 py-3 text-sm text-[var(--mute)]"
        >
          Connect a warehouse →
        </Link>
      ) : datasources.length === 1 && selected ? (
        <SelectedCard datasource={selected} />
      ) : (
        <div className="flex flex-col gap-1.5">
          {datasources.map((ds) => (
            <Row
              key={ds.name}
              datasource={ds}
              active={ds.name === selected?.name}
              onSelect={() => select(ds.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
