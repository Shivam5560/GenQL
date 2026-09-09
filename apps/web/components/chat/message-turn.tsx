import type { TurnRecord } from '@/lib/types';
import { SqlCard } from './sql-card';

export function MessageTurn({
  turn,
  revealed,
  onReveal,
  accessToken,
  threadId,
}: {
  turn: TurnRecord;
  revealed: boolean;
  onReveal?: () => void;
  accessToken: string;
  threadId: string;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="max-w-[70%] self-end rounded-lg rounded-br-sm bg-[var(--ink)] px-4 py-2.5 text-sm text-[var(--bg)]">
        {turn.question}
      </div>
      <div className="flex w-full flex-col gap-3">
        {turn.clarifying_question ? (
          <p className="max-w-[64ch] text-sm text-[var(--mute)]">{turn.clarifying_question}</p>
        ) : (
          <>
            {turn.recap && <p className="max-w-[64ch] text-sm text-[var(--mute)]">{turn.recap}</p>}
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
