import type { TurnRecord } from '@/lib/types';
import { Assumptions, Clarification } from './clarification';
import { SqlCard } from './sql-card';

export function MessageTurn({
  turn,
  revealed,
  onReveal,
  accessToken,
  threadId,
  onAnswer,
}: {
  turn: TurnRecord;
  revealed: boolean;
  onReveal?: () => void;
  accessToken: string;
  threadId: string;
  /** Answers this turn's clarifying question directly, from a tapped chip.
      Omitted for a turn that is no longer the one being answered, which is
      what makes the chips disappear once the thread has moved on. */
  onAnswer?: (answer: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="max-w-[70%] self-end rounded-lg rounded-br-sm bg-[var(--ink)] px-4 py-2.5 text-sm text-[var(--bg)]">
        {turn.question}
      </div>
      <div className="flex w-full flex-col gap-3">
        {turn.clarifying_question ? (
          <Clarification
            question={turn.clarifying_question}
            suggestedAnswer={turn.suggested_answer}
            options={turn.clarification_options}
            onAnswer={onAnswer}
          />
        ) : (
          <>
            {turn.recap && <p className="max-w-[64ch] text-sm text-[var(--mute)]">{turn.recap}</p>}
            <Assumptions assumed={turn.assumed ?? []} />
            {/* Every unrevealed turn stays executable, not just the latest one:
                `revealed` alone decides whether results are shown. */}
            <SqlCard
              turn={turn}
              revealed={revealed}
              onReveal={onReveal}
              accessToken={accessToken}
              threadId={threadId}
            />
          </>
        )}
      </div>
    </div>
  );
}
