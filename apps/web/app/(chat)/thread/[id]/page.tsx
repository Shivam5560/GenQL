'use client';

import { useEffect, useState, use as usePromise } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { getThread, resumeTurn, startTurn } from '@/lib/api-client';
import { toLocalTurnRecord } from '@/lib/recap';
import { MessageTurn } from '@/components/chat/message-turn';
import { Button } from '@/components/ui/button';
import type { ThreadDetail } from '@/lib/types';

const GENERIC_ERROR = 'Something went wrong — try again.';

function ThreadSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-6 overflow-y-auto px-7 py-6">
      <div className="ml-auto h-9 w-2/3 max-w-[420px] animate-pulse rounded-lg bg-[var(--panel-2)]" />
      <div className="h-28 w-full animate-pulse rounded-lg bg-[var(--panel-2)]" />
    </div>
  );
}

export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: threadId } = usePromise(params);
  const { session } = useAuth();
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());
  const [loadFailed, setLoadFailed] = useState(false);

  function loadThread() {
    if (!session) return;
    getThread(session.accessToken, threadId)
      .then((loaded) => {
        setDetail(loaded);
        // Every turn loaded from history was already seen by the user in an
        // earlier session — reveal all of them immediately.
        setRevealedIds(new Set(loaded.turns.map((t) => t.turn_id)));
        setLoadFailed(false);
      })
      .catch(() => {
        setLoadFailed(true);
        toast.error(GENERIC_ERROR);
      });
  }

  useEffect(() => {
    loadThread();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, threadId]);

  if (!session || (!detail && !loadFailed)) {
    return (
      <>
        <div className="flex items-center justify-between border-b border-[var(--line)] px-7 py-3.5">
          <div className="h-4 w-40 animate-pulse rounded bg-[var(--panel-2)]" />
        </div>
        <ThreadSkeleton />
      </>
    );
  }

  if (!detail) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-3">
        <p className="text-sm text-[var(--mute)]">Couldn&apos;t load this thread.</p>
        <Button type="button" onClick={loadThread}>
          Retry
        </Button>
      </main>
    );
  }

  const latest = detail.turns[detail.turns.length - 1];
  const awaitingClarification = Boolean(latest?.clarifying_question);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !detail || !input.trim()) return;
    setSubmitting(true);
    try {
      const question = input;
      const response = awaitingClarification
        ? await resumeTurn(session.accessToken, threadId, question)
        : await startTurn(session.accessToken, {
            question,
            datasource: detail.summary.datasource_name,
            thread_id: threadId,
          });
      // Only clear the box once the request has actually succeeded, so a
      // failure leaves the user's typed question where they can retry it.
      setInput('');
      const nextSequence = detail.turns.length;
      const localTurn = toLocalTurnRecord(question, nextSequence, response);
      setDetail((prev) => (prev ? { ...prev, turns: [...prev.turns, localTurn] } : prev));
      // A turn with no clarifying question has data to reveal on demand;
      // one that paused again has nothing to gate, so it may as well count
      // as already revealed — there is no ResultTable to withhold either way.
      if (localTurn.clarifying_question) {
        setRevealedIds((prev) => new Set(prev).add(localTurn.turn_id));
      }
    } catch {
      toast.error(GENERIC_ERROR);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between border-b border-[var(--line)] px-7 py-3.5">
        <h1 className="text-sm font-semibold">{detail.summary.title}</h1>
        <span className="font-eyebrow text-[0.68rem] text-[var(--mute)]">
          THREAD {detail.summary.thread_id}
        </span>
      </div>
      <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-6 overflow-y-auto px-7 py-6">
        {detail.turns.map((turn) => (
          <MessageTurn
            key={turn.turn_id}
            turn={turn}
            revealed={revealedIds.has(turn.turn_id)}
            onReveal={() => setRevealedIds((prev) => new Set(prev).add(turn.turn_id))}
            accessToken={session.accessToken}
            threadId={threadId}
          />
        ))}
      </div>
      <form onSubmit={onSubmit} className="border-t border-[var(--line)] px-7 py-4">
        <div className="mx-auto flex max-w-[900px] items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2.5 pl-4">
          <input
            className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)]"
            placeholder={
              awaitingClarification
                ? 'Answer the question above…'
                : `Ask a follow-up about ${detail.summary.datasource_name}…`
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <Button type="submit" disabled={submitting || !input.trim()}>
            {submitting ? 'Asking…' : 'Send'}
          </Button>
        </div>
      </form>
    </>
  );
}
