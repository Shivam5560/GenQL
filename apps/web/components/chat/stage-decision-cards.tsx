import type { Decision } from './stage-decisions';

/**
 * The rail's top tier: what a reviewer would argue with.
 *
 * Three cards at most, and often fewer — `buildDecisions` returns only the ones
 * whose facts are actually on the turn. The accented card is the one carrying
 * something the person themselves said, which is the only thing on this panel
 * that is not the machine's own account of itself.
 */
function Card({ decision }: { decision: Decision }) {
  return (
    <article
      className={`border-l-2 bg-[var(--panel)] px-3 py-2.5 ${
        decision.accent ? 'border-l-[var(--brand)]' : 'border-l-[var(--mute)]'
      }`}
    >
      <p className="flex items-center gap-2">
        <span
          className={`font-eyebrow text-[0.58rem] uppercase tracking-[0.14em] ${
            decision.accent ? 'text-[var(--brand)]' : 'text-[var(--mute)]'
          }`}
        >
          {decision.eyebrow}
        </span>
        {decision.aside && (
          <span className="ml-auto shrink-0 font-mono text-[0.58rem] tabular-nums text-[var(--mute)] opacity-70">
            {decision.aside}
          </span>
        )}
      </p>

      {decision.lead && (
        <p className="mt-1.5 text-[0.8rem] leading-snug text-[var(--ink)]">{decision.lead}</p>
      )}

      {decision.rows.length > 0 && (
        <dl className="mt-2 flex flex-col gap-1">
          {decision.rows.map((row) => (
            <div key={row.label} className="flex gap-2">
              <dt className="w-[4.6rem] shrink-0 font-mono text-[0.58rem] leading-relaxed text-[var(--mute)] opacity-70">
                {row.label}
              </dt>
              <dd className="min-w-0 break-words text-[0.72rem] leading-relaxed text-[var(--ink)]">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {decision.note && (
        <p className="mt-2 text-[0.66rem] leading-snug text-[var(--mute)] opacity-80">
          {decision.note}
        </p>
      )}
    </article>
  );
}

export function DecisionCards({ decisions }: { decisions: Decision[] }) {
  // Nothing at all when nothing was decided — no heading over an empty region.
  // A turn that ran straight through genuinely has no contested reading, and
  // saying so with silence is more honest than an empty card.
  if (decisions.length === 0) return null;

  return (
    // A labelled region, not a bare div: the rail says the same fact twice on
    // purpose — once as a decision, once as a step in the trail — so a reader
    // (and a test) needs a way to say which of the two they mean.
    <section aria-label="What decided this answer" className="flex shrink-0 flex-col gap-2">
      <p className="font-eyebrow text-[0.58rem] uppercase tracking-[0.16em] text-[var(--mute)] opacity-70">
        What decided this answer
      </p>
      {decisions.map((decision) => (
        <Card key={decision.key} decision={decision} />
      ))}
    </section>
  );
}
