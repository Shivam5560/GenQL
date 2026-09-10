import type { TurnRecord } from '@/lib/types';
import { Assumptions, Clarification } from './clarification';
import { SqlCard } from './sql-card';

/**
 * One question and what came back, set as an entry rather than a chat.
 *
 * The question used to sit in a dark bubble against the right margin, which
 * is the shape of a messaging app and carries that app's promise: that what
 * you sent is a message, and what comes back is a reply you skim. This is not
 * that. What comes back is a statement someone has to read closely enough to
 * defend, so the question is set as the heading of the section that answers
 * it — in the serif, at the left margin, where a reader's eye already starts.
 * The rule above each entry does the work the bubble's alignment used to do:
 * it says where one question ends and the next begins.
 */
export function MessageTurn({
  turn,
  revealed,
  onReveal,
  accessToken,
  threadId,
  onAnswer,
  /** False for the opening turn, which needs no rule above it. */
  divided = true,
  resumes = false,
  hasDiscussion = false,
  discussionActive = false,
  onOpenDiscussion,
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
  divided?: boolean;
  /** True when this turn's text answers the previous turn's clarifying
      question rather than asking something new. */
  resumes?: boolean;
  /** True when this turn's pipeline trail was captured this session, so its
      SqlCard can offer a "Discussion" button. Reloaded history has none. */
  hasDiscussion?: boolean;
  /** True when the right rail is currently showing this turn's trail. */
  discussionActive?: boolean;
  onOpenDiscussion?: () => void;
}) {
  return (
    <article
      className={`flex flex-col gap-4 ${
        divided && !resumes ? 'border-t border-[var(--line)] pt-8' : ''
      }`}
    >
      {/* A resumed turn's "question" is an answer — "the full available
          history" — and setting that at headline weight asserts it as a
          question the person asked, which it is not. It belongs to the entry
          above it, so it keeps that entry's rule off and states what it is. */}
      {resumes ? (
        <p className="max-w-[62ch] text-[0.95rem]">
          <span className="text-[var(--mute)]">Answered</span> {turn.question}
        </p>
      ) : (
        <h2 className="max-w-[34ch] font-serif text-[1.55rem] font-normal leading-[1.25] tracking-[-0.01em]">
          {turn.question}
        </h2>
      )}
      {turn.clarifying_question ? (
        <Clarification
          question={turn.clarifying_question}
          suggestedAnswer={turn.suggested_answer}
          options={turn.clarification_options}
          onAnswer={onAnswer}
        />
      ) : (
        <>
          {turn.recap && (
            <p className="max-w-[62ch] text-[0.92rem] leading-relaxed text-[var(--mute)]">
              {turn.recap}
            </p>
          )}
          <Assumptions assumed={turn.assumed ?? []} />
          {/* Every unrevealed turn stays executable, not just the latest one:
              `revealed` alone decides whether results are shown. */}
          <SqlCard
            turn={turn}
            revealed={revealed}
            onReveal={onReveal}
            accessToken={accessToken}
            threadId={threadId}
            hasDiscussion={hasDiscussion}
            discussionActive={discussionActive}
            onOpenDiscussion={onOpenDiscussion}
          />
        </>
      )}
    </article>
  );
}
