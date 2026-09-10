const GATES = [
  {
    label: 'AMBIGUITY',
    heading: 'It asks instead of assuming',
    body: '"Distinct" has two readings in your sentence. GenQL stops, names both, and waits — one question, not a wrong table.',
  },
  {
    label: 'COST',
    heading: 'Nothing expensive runs silently',
    body: 'Estimated scan is shown before execution, and nothing runs until you press it. Reads only — no warehouse writes.',
  },
  {
    label: 'CRITIQUE',
    heading: 'The draft is reviewed before you see it',
    body: 'Four candidates, dry-run against the real schema, ranked and critiqued. You get the survivor and the reasons it survived.',
  },
];

export function DirectionGates() {
  return (
    <section className="border-t border-[var(--line)] px-6 py-16 md:px-10 md:py-24">
      <div className="mx-auto max-w-[1400px]">
        <span className="font-eyebrow text-[10px] uppercase tracking-[0.2em] text-[var(--mute)]">
          03 — THE GATES
        </span>
        <h2 className="mt-4 max-w-[22ch] font-serif text-[clamp(2rem,4vw,3.6rem)] font-light leading-tight tracking-[-0.02em]">
          Three places GenQL{' '}
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
