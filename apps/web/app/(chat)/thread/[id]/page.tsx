'use client';

import { useCallback, useEffect, useRef, useState, use as usePromise } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { ApiError, getThread, streamTurn } from '@/lib/api-client';
import { toLocalTurnRecord } from '@/lib/recap';
import { takeHandoff } from '@/lib/pending-turn-handoff';
import { useThreadList } from '@/lib/thread-list-provider';
import { MessageTurn } from '@/components/chat/message-turn';
import { PendingTurn } from '@/components/chat/pending-turn';
import { StageRail } from '@/components/chat/stage-rail';
import { Button } from '@/components/ui/button';
import type {
  PendingTurn as PendingTurnState,
  StageEvent,
  ThreadDetail,
  TurnResponse,
} from '@/lib/types';

const GENERIC_ERROR = 'Something went wrong — try again.';

function ThreadSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-6 overflow-y-auto px-7 py-6">
      <div className="ml-auto h-9 w-2/3 max-w-[420px] animate-pulse rounded-lg bg-[var(--panel-2)]" />
      <div className="h-28 w-full animate-pulse rounded-lg bg-[var(--panel-2)]" />
    </div>
  );
}

/**
 * Keyed by thread id so switching threads remounts rather than reconciles.
 *
 * Every piece of per-thread state below — the transcript, the in-flight turn,
 * which results have been revealed — would otherwise have to be reset by hand
 * on each navigation, and the one that got forgotten would show the previous
 * thread's answer under the new thread's question.
 */
export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: threadId } = usePromise(params);
  return <ThreadView key={threadId} threadId={threadId} />;
}

function ThreadView({ threadId }: { threadId: string }) {
  const { session } = useAuth();
  const { refresh } = useThreadList();

  // Read once, at mount, and consumed: the new-thread composer left the first
  // question here and navigated without waiting for an answer.
  const [handoff] = useState(() =>
    typeof window === 'undefined' ? null : takeHandoff(threadId),
  );
  const [pending, setPending] = useState<PendingTurnState | null>(() =>
    handoff
      ? {
          localId: 'initial',
          question: handoff.question,
          stages: [],
          startedAt: Date.now(),
          error: null,
        }
      : null,
  );
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [input, setInput] = useState('');
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());
  const [loadFailed, setLoadFailed] = useState(false);
  // Stages of the most recently finished turn, so the rail keeps reporting
  // what the pipeline did instead of blanking the moment the answer lands.
  const [lastStages, setLastStages] = useState<StageEvent[]>([]);
  // One in-flight turn per thread, matching the server's own thread lock.
  const abortRef = useRef<AbortController | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const accessToken = session?.accessToken;

  const loadThread = useCallback(() => {
    if (!accessToken) return;
    getThread(accessToken, threadId)
      .then((loaded) => {
        setDetail(loaded);
        // Every turn loaded from history was already seen in an earlier
        // session — reveal all of them immediately.
        setRevealedIds(new Set(loaded.turns.map((t) => t.turn_id)));
        setLoadFailed(false);
      })
      .catch((reason: unknown) => {
        setLoadFailed(true);
        // A thread whose first turn has not been recorded yet genuinely does
        // not exist server-side; that is an empty thread, not a broken one,
        // and does not deserve a toast.
        if (!(reason instanceof ApiError && reason.status === 404)) toast.error(GENERIC_ERROR);
      });
  }, [accessToken, threadId]);

  /**
   * Open the stream for a turn whose bubble is already on screen.
   *
   * Deliberately separate from `askQuestion` below: this one starts no state,
   * so the mount effect can call it without seeding a render, and the very
   * first turn's pending state comes from the handoff at construction time.
   */
  const openStream = useCallback(
    (question: string, datasource: string, answer?: string) => {
      if (!accessToken) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const collected: StageEvent[] = [];

      void streamTurn(
        accessToken,
        { question, datasource, thread_id: threadId, ...(answer !== undefined ? { answer } : {}) },
        {
          onStage: (stage) => {
            collected.push(stage);
            setPending((prev) => (prev ? { ...prev, stages: [...collected] } : prev));
          },
          onWarning: (warning) => toast.warning(warning.detail),
          onError: (error) => setPending((prev) => (prev ? { ...prev, error } : prev)),
          onTerminal: (response: TurnResponse) => {
            setDetail((prev) => {
              const turns = prev?.turns ?? [];
              const localTurn = toLocalTurnRecord(question, turns.length, response);
              // A paused turn has no ResultTable to gate, so it counts as
              // already revealed; a finished one keeps its Execute gate.
              if (localTurn.clarifying_question) {
                setRevealedIds((ids) => new Set(ids).add(localTurn.turn_id));
              }
              const summary = prev?.summary ?? {
                thread_id: threadId,
                datasource_name: datasource,
                title: question,
                created_at: new Date().toISOString(),
                last_active_at: new Date().toISOString(),
              };
              return { summary, turns: [...turns, localTurn] };
            });
            setLastStages([...collected]);
            setPending(null);
            setLoadFailed(false);
            // The sidebar learns of a thread only once its first turn is
            // recorded, which is exactly now.
            void refresh();
          },
        },
        controller.signal,
      );
    },
    [accessToken, threadId, refresh],
  );

  /** Send a question typed into the composer: bubble first, then the stream. */
  const askQuestion = useCallback(
    (question: string, datasource: string, answer?: string) => {
      setPending({
        localId: `pending-${Date.now()}`,
        question,
        stages: [],
        startedAt: Date.now(),
        error: null,
      });
      setLastStages([]);
      openStream(question, datasource, answer);
    },
    [openStream],
  );

  useEffect(() => {
    if (!accessToken) return;
    if (handoff) {
      openStream(handoff.question, handoff.datasource);
      return;
    }
    loadThread();
  }, [accessToken, handoff, openStream, loadThread]);

  useEffect(() => () => abortRef.current?.abort(), []);

  /**
   * Abandon a turn that is taking too long.
   *
   * Aborting the stream is a client-side hang-up, not a server-side cancel:
   * the pipeline finishes whatever it is doing and the turn is still recorded
   * server-side. That is the honest thing to say in the message below, and it
   * is why the composer is handed straight back rather than the turn being
   * removed from history.
   */
  const stop = useCallback(() => {
    abortRef.current?.abort();
    setPending((prev) =>
      prev
        ? {
            ...prev,
            error: {
              error: 'Stopped',
              detail:
                'You stopped waiting for this answer. GenQL may still finish it — reload the ' +
                'thread in a moment to see whether it did.',
            },
          }
        : prev,
    );
  }, []);

  // Keep the newest turn in view as stages and answers arrive.
  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight });
  }, [detail?.turns.length, pending?.stages.length, pending?.error]);

  if (!session || (!detail && !loadFailed && !pending)) {
    return (
      <>
        <div className="flex items-center justify-between border-b border-[var(--line)] px-7 py-3.5">
          <div className="h-4 w-40 animate-pulse rounded bg-[var(--panel-2)]" />
        </div>
        <ThreadSkeleton />
      </>
    );
  }

  if (!detail && !pending) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-3">
        <p className="text-sm text-[var(--mute)]">Couldn&apos;t load this thread.</p>
        <Button type="button" onClick={loadThread}>
          Retry
        </Button>
      </main>
    );
  }

  const turns = detail?.turns ?? [];
  const latest = turns[turns.length - 1];
  const awaitingClarification = Boolean(latest?.clarifying_question);
  const suggestion = awaitingClarification ? latest?.suggested_answer?.trim() || null : null;
  const datasourceName = detail?.summary.datasource_name ?? handoff?.datasource ?? '';
  const running = pending !== null && pending.error === null;

  /** Answer the pending clarifying question with exactly this text. */
  function answer(text: string) {
    setInput('');
    askQuestion(text, datasourceName, text);
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (running) return;
    const typed = input.trim();
    // Enter on an empty composer accepts the suggestion, so the common case
    // — "yes, the obvious reading" — costs one keystroke rather than a
    // typed sentence. Without a suggestion to accept there is nothing to
    // submit, and the button stays disabled.
    if (!typed) {
      if (awaitingClarification && suggestion) answer(suggestion);
      return;
    }
    // Cleared immediately: the question is already on screen as a bubble, and
    // a failure keeps it there with a Retry rather than losing it.
    setInput('');
    askQuestion(typed, datasourceName, awaitingClarification ? typed : undefined);
  }

  return (
    <>
      <div className="flex items-center justify-between gap-4 border-b border-[var(--line)] px-7 py-3.5">
        <h1 className="truncate text-sm font-semibold">
          {detail?.summary.title ?? pending?.question}
        </h1>
        <div className="flex shrink-0 items-center gap-2.5">
          {/* A thread is bound to the datasource its first question went to
              and cannot be moved — so this states it rather than offering a
              picker that would silently mean "ask this again somewhere else".
              Switching warehouses is a new thread, and the sidebar has one. */}
          {datasourceName && (
            <span
              title={`This thread asks ${datasourceName}`}
              className="max-w-[14rem] truncate rounded-full border border-[var(--line)] px-2.5 py-0.5 font-mono text-[0.68rem] text-[var(--mute)]"
            >
              {datasourceName}
            </span>
          )}
          <span className="font-eyebrow text-[0.68rem] text-[var(--mute)]">
            THREAD {threadId.slice(0, 8)}
          </span>
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div
            ref={transcriptRef}
            className="mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-6 overflow-y-auto px-7 py-6"
          >
            {turns.map((turn) => (
              <MessageTurn
                key={turn.turn_id}
                turn={turn}
                revealed={revealedIds.has(turn.turn_id)}
                onReveal={() => setRevealedIds((prev) => new Set(prev).add(turn.turn_id))}
                accessToken={session.accessToken}
                threadId={threadId}
                // Only the turn actually waiting for an answer is answerable,
                // and only while nothing else is in flight: chips on an older
                // paused turn would resume a pause that has already been
                // resumed.
                onAnswer={turn === latest && awaitingClarification && !running ? answer : undefined}
              />
            ))}
            {pending && (
              <PendingTurn
                turn={pending}
                onRetry={() => askQuestion(pending.question, datasourceName)}
                onStop={running ? stop : undefined}
              />
            )}
          </div>
          <form onSubmit={onSubmit} className="border-t border-[var(--line)] px-7 py-4">
            <div className="mx-auto flex max-w-[900px] items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2.5 pl-4">
              <input
                className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)] disabled:opacity-60"
                placeholder={
                  running
                    ? 'Waiting for the current answer…'
                    : suggestion
                      ? `Press enter for “${suggestion}”, or answer differently…`
                      : awaitingClarification
                        ? 'Answer the question above…'
                        : `Ask a follow-up about ${datasourceName || 'your data'}…`
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={running}
              />
              <Button type="submit" disabled={running || (!input.trim() && !suggestion)}>
                Send
              </Button>
            </div>
          </form>
        </div>
        <StageRail
          stages={pending ? pending.stages : lastStages}
          running={running}
          startedAt={pending?.startedAt ?? null}
          failed={pending?.error != null}
        />
      </div>
    </>
  );
}
