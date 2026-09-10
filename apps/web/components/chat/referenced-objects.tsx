/**
 * What the statement above actually reads.
 *
 * Named "Reads" rather than "Tables" because that is the question being
 * answered — a person checking a query wants to know which of their objects
 * it touches, and a bare list under a neutral noun makes them work out the
 * relationship themselves.
 */
export function ReferencedObjects({ objects }: { objects: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-t border-[var(--line)] bg-[var(--panel-2)] px-4 py-2">
      <span className="text-[0.72rem] text-[var(--mute)]">Reads</span>
      {objects.map((object) => (
        <span key={object} className="font-mono text-[0.72rem] text-[var(--ink)]">
          {object}
        </span>
      ))}
    </div>
  );
}
