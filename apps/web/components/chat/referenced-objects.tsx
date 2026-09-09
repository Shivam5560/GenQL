export function ReferencedObjects({ objects }: { objects: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-t border-[var(--line)] bg-[var(--panel-2)] px-3.5 py-2">
      <span className="font-eyebrow text-[0.62rem] uppercase tracking-wide text-[var(--mute)]">Tables</span>
      {objects.map((object) => (
        <span
          key={object}
          className="font-eyebrow rounded border border-[var(--line)] px-2 py-0.5 text-[0.64rem] uppercase text-[var(--mute)]"
        >
          {object}
        </span>
      ))}
    </div>
  );
}
