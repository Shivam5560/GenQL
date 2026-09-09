'use client';

import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listDatasources, startTurn } from '@/lib/api-client';
import { AmbientField } from '@/components/hero/ambient-field';
import { HeroHeadline } from '@/components/hero/hero-headline';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Datasource } from '@/lib/types';

const GENERIC_ERROR = 'Something went wrong — try again.';

export default function NewThreadPage() {
  const { session } = useAuth();
  const router = useRouter();
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [datasource, setDatasource] = useState<string>('');
  const [question, setQuestion] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken)
      .then((list) => {
        setDatasources(list);
        if (list[0]) setDatasource(list[0].name);
      })
      .catch(() => {
        setDatasources([]);
        setError(GENERIC_ERROR);
      });
  }, [session]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !datasource || !question.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await startTurn(session.accessToken, { question, datasource });
      router.push(`/thread/${response.thread_id}`);
    } catch {
      setError(GENERIC_ERROR);
    } finally {
      setSubmitting(false);
    }
  }

  const selected = datasources.find((ds) => ds.name === datasource);

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
              <Select value={datasource} onValueChange={(next) => setDatasource(next ?? '')}>
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
              {selected && (
                <span className="truncate pr-1 font-mono text-xs text-[var(--mute)]">
                  {selected.dialect}
                </span>
              )}
            </div>
            <div className="mt-3 h-px bg-[var(--line)]" />
            <div className="flex items-center gap-2.5 p-2.5 pl-4">
              <input
                className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)]"
                placeholder={
                  datasource ? `Ask a question about ${datasource}…` : 'Ask a question about your data…'
                }
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <Button type="submit" disabled={submitting || !datasource || !question.trim()}>
                {submitting ? 'Asking…' : 'Send'}
              </Button>
            </div>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      </main>
    </div>
  );
}
