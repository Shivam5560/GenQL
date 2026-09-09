'use client';

import { usePointerTilt } from '@/lib/use-pointer-tilt';
import type { Datasource } from '@/lib/types';

export function DatasourceCard({ datasource }: { datasource: Datasource }) {
  // The one card in the app that stands for a physical thing you are pointed
  // at, so it is the one that gets depth. Four degrees, damped by the
  // transition in `.gq-tilt`; nothing attaches on touch or under reduced
  // motion.
  const { ref, tiltProps } = usePointerTilt<HTMLDivElement>(4);

  return (
    <div>
      <p className="font-eyebrow mb-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
        Datasource
      </p>
      <div
        ref={ref}
        {...tiltProps}
        className="gq-tilt rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3"
      >
        <div className="text-sm font-semibold">{datasource.name}</div>
        <div className="mt-0.5 font-mono text-xs text-[var(--mute)]">{datasource.dialect}</div>
      </div>
    </div>
  );
}
