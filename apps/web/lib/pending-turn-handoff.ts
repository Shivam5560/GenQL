/**
 * Carries the first question of a new thread across one navigation.
 *
 * The new-thread composer used to `await` the whole turn and only then push
 * to `/thread/<id>` — which is most of the four-second wait the redesign
 * removes. Now it mints the thread id itself, hands the question over here,
 * and navigates immediately, so the thread page can render the bubble and
 * open the stream on its first paint.
 *
 * `sessionStorage` rather than a query parameter: the question is often long
 * and occasionally sensitive, and a URL is shared, logged, and kept in
 * history. It is read exactly once and cleared, so a reload does not re-ask
 * a question that already ran.
 */

const KEY = 'genql:pending-turn';

export interface TurnHandoff {
  threadId: string;
  question: string;
  datasource: string;
}

/** A thread id in the same shape the API generates, so both look alike in logs. */
export function newThreadId(): string {
  const random =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(16).slice(2).padEnd(32, '0');
  return `t-${random}`;
}

export function stashHandoff(handoff: TurnHandoff): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(handoff));
  } catch {
    // Storage disabled (private mode, a strict policy). The thread page will
    // simply show an empty thread; nothing is lost but the auto-start.
  }
}

/** Returns the handoff for this thread and removes it, or null. */
export function takeHandoff(threadId: string): TurnHandoff | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TurnHandoff;
    if (parsed.threadId !== threadId) return null;
    sessionStorage.removeItem(KEY);
    return parsed;
  } catch {
    return null;
  }
}
