import type { Datasource } from '@/lib/types';

export function DatasourceCard({ datasource }: { datasource: Datasource }) {
  return (
    <div>
      <p className="font-eyebrow mb-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
        Datasource
      </p>
      <div className="rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3">
        <div className="text-sm font-semibold">{datasource.name}</div>
        <div className="mt-0.5 text-xs text-[var(--mute)]">{datasource.dialect}</div>
      </div>
    </div>
  );
}
