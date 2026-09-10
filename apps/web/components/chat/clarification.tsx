'use client';

/**
 * A paused turn: the question, plus the answers worth one tap.
 *
 * The screen this replaces was a sentence and an empty text box, and the only
 * way past it was to type a sentence of your own — three times in a row on a
 * question that had not yet returned a row. The gate already knows the
 * reading it would apply, so offering it is strictly more information than
 * asking for prose, and costs the person a click.
 *
 * The suggestion is separated from the alternatives because they are not
 * equals: the first is what happens by default (pressing enter on an empty
 * composer submits it), the rest are merely nearby. Both are absent on a turn
 * reloaded from history, which the backend does not persist suggestions for —
 * so the question alone has to render correctly, and does.
 */
export function Clarification({
  question,
  suggestedAnswer,
  options,
  onAnswer,
}: {
  question: string;
  suggestedAnswer?: string | null;
  options?: string[];
  onAnswer?: (answer: string) => void;
}) {
  const suggestion = suggestedAnswer?.trim() || null;
  // An alternative identical to the suggestion is not an alternative; it
  // would render as the same words twice, one of them looking authoritative.
  //
  // Compared case-insensitively because that is exactly how the duplicate
  // arrives: the gate suggests "all available history" and lists "All
  // available history" among the options, and an exact match let both
  // through — two chips, same answer, one wearing the default badge.
  const seen = new Set<string>();
  const alternatives = (options ?? [])
    .map((option) => option.trim())
    .filter((option) => {
      const key = option.toLowerCase();
      if (option.length === 0 || key === suggestion?.toLowerCase() || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  const answerable = onAnswer !== undefined;

  return (
    <div className="flex max-w-[62ch] flex-col gap-3">
      <p className="text-[0.95rem] leading-relaxed">{question}</p>
      {answerable && (suggestion || alternatives.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {suggestion && (
            <button
              type="button"
              onClick={() => onAnswer(suggestion)}
              className="rounded-full border border-[var(--brand)] px-3.5 py-1.5 text-[0.84rem] text-[var(--ink)]"
            >
              {suggestion}
              <span className="pl-1.5 text-[0.74rem] text-[var(--mute)]">default</span>
            </button>
          )}
          {alternatives.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onAnswer(option)}
              className="rounded-full border border-[var(--line)] px-3.5 py-1.5 text-[0.84rem] text-[var(--mute)]"
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * What was decided without asking, on a turn that went ahead and answered.
 *
 * This is the other half of the bargain: the gate stops asking after one
 * question, so everything it settled on its own has to be visible, or the
 * user is reading an answer to a question they cannot see. Stated as
 * plain values rather than rule names, since the reader is checking whether
 * the answer means what they wanted.
 */
export function Assumptions({ assumed }: { assumed: [string, string][] }) {
  if (assumed.length === 0) return null;

  return (
    <div className="flex max-w-[62ch] flex-col gap-1.5 border-l-2 border-[var(--brand)] pl-3.5">
      <p className="text-[0.86rem] text-[var(--mute)]">
        Decided without asking. Say so in a follow-up to change one.
      </p>
      {assumed.map(([dimension, value]) => (
        <p key={dimension} className="text-[0.86rem] text-[var(--mute)]">
          <span className="font-mono text-[0.82rem] text-[var(--ink)]">{dimension}</span> {value}
        </p>
      ))}
    </div>
  );
}
