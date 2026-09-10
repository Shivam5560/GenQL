'use client';

import { useState } from 'react';
import type { CSSProperties } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { useDatasources } from '@/lib/datasource-provider';
import { newThreadId, stashHandoff } from '@/lib/pending-turn-handoff';
import { AmbientField } from '@/components/hero/ambient-field';
import { HeroHeadline } from '@/components/hero/hero-headline';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function NewThreadPage() {
  const { session } = useAuth();
  const router = useRouter();
  // One list, shared with the sidebar, so picking a warehouse in either place
  // means the same thing — see `lib/datasource-provider`.
  const { datasources, selected, select, loading } = useDatasources();
  const [question, setQuestion] = useState('');

  /**
   * Navigates immediately rather than awaiting the turn.
   *
   * The thread id is minted here and handed to the thread page along with the
   * question, so the bubble is on screen before a single pipeline stage has
   * run. The old version awaited `POST /v1/queries` — the whole four seconds —
   * with the button reading "Asking…" and the screen otherwise unchanged.
   */
  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !selected || !question.trim()) return;
    const threadId = newThreadId();
    stashHandoff({ threadId, question: question.trim(), datasource: selected.name });
    router.push(`/thread/${threadId}`);
  }

  const noDatasources = !loading && datasources.length === 0;

  return (
    <div className="relative isolate flex flex-1 flex-col overflow-hidden">
      <AmbientField />
      <main className="mx-auto flex w-full max-w-[820px] flex-1 flex-col justify-center px-7 py-16">
        <HeroHeadline />
        <form
          onSubmit={onSubmit}
          className="gq-rise mt-10 flex w-full flex-col gap-3"
          style={{ '--gq-delay': '250ms' } as CSSProperties}
        >
          <div className="gq-glass rounded-lg border border-[var(--line)]">
            <div className="flex items-center justify-between gap-3 px-3 pt-3">
              {/* A picker only when there is a pick to make. With one
                  warehouse connected this reads as a label, which is what it
                  is. */}
              {datasources.length > 1 ? (
                <Select value={selected?.name ?? ''} onValueChange={(next) => next && select(next)}>
                  <SelectTrigger className="min-w-[13rem]">
                    <SelectValue placeholder="Choose a datasource" />
                  </SelectTrigger>
                  <SelectContent>
                    {datasources.map((ds) => (
                      <SelectItem key={ds.name} value={ds.name}>
                        {ds.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <span className="truncate pl-1 text-sm font-semibold">{selected?.name ?? ''}</span>
              )}
              {selected && (
                <span className="truncate pr-1 font-mono text-xs text-[var(--mute)]">
                  {selected.endpoint ?? selected.dialect}
                </span>
              )}
            </div>
            <div className="mt-3 h-px bg-[var(--line)]" />
            <div className="flex items-center gap-2.5 p-2.5 pl-4">
              <input
                className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)]"
                placeholder={
                  selected
                    ? `Ask a question about ${selected.name}…`
                    : 'Ask a question about your data…'
                }
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                autoFocus
              />
              <Button
                type="submit"
                disabled={!selected || !question.trim()}
                className="font-eyebrow text-[0.68rem] uppercase tracking-[0.12em]"
              >
                Send
              </Button>
            </div>
          </div>
          {noDatasources && (
            <p className="text-sm text-[var(--mute)]">
              No datasources yet.{' '}
              <a className="underline" href="/datasources">
                Connect a warehouse
              </a>{' '}
              to ask your first question.
            </p>
          )}
        </form>
      </main>
    </div>
  );
}
