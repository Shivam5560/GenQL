const GATES = [
  {
    label: 'AMBIGUITY',
    heading: 'It asks instead of assuming',
    body: '"Distinct" has two readings in your sentence. AuraSQL stops, names both, and waits for one answer instead of picking a table for you.',
  },
  {
    label: 'COST',
    heading: 'Nothing expensive runs silently',
    body: 'The estimated scan is shown before anything executes, and nothing runs until you say so. Reads only, never writes to your warehouse.',
  },
  {
    label: 'CRITIQUE',
    heading: 'The draft is reviewed before you see it',
    body: 'Four candidates, checked against the real schema, ranked and critiqued. You get the one that survived, and why it did.',
  },
];

export function DirectionGates() {
  return (
    <section className="border-t border-[var(--line)] px-6 py-16 md:px-10 md:py-24">
      <div className="mx-auto max-w-[1400px]">
        <span className="font-eyebrow text-[10px] uppercase tracking-[0.2em] text-[var(--mute)]">
          02 — THE GATES
        </span>
        <h2 className="mt-4 max-w-[22ch] font-serif text-[clamp(2rem,4vw,3.6rem)] font-light leading-tight tracking-[-0.02em]">
          Three places AuraSQL{' '}
          <span className="font-extralight italic text-[var(--mute)]">refuses to guess.</span>
        </h2>

        <div className="mt-12 grid gap-px border border-[var(--line)] bg-[var(--line)] md:grid-cols-3">
          {GATES.map((gate) => (
            <div
              key={gate.label}
              className="flex flex-col gap-3 bg-[var(--bg)] p-8 transition-colors hover:bg-[var(--panel)] md:p-10"
            >
              <span className="font-eyebrow text-[10px] uppercase tracking-[0.16em] text-[var(--brand)]">
                {gate.label}
              </span>
              <h3 className="font-serif text-2xl font-light">{gate.heading}</h3>
              <p className="text-[1rem] leading-relaxed text-[var(--mute)]">{gate.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
