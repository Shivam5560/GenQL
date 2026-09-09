'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listDatasources, startTurn } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Datasource } from '@/lib/types';

export default function NewThreadPage() {
  const { session } = useAuth();
  const router = useRouter();
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [datasource, setDatasource] = useState<string>('');
  const [question, setQuestion] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken)
      .then((list) => {
        setDatasources(list);
        if (list[0]) setDatasource(list[0].name);
      })
      .catch(() => setDatasources([]));
  }, [session]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !datasource || !question.trim()) return;
    setSubmitting(true);
    try {
      const response = await startTurn(session.accessToken, { question, datasource });
      router.push(`/thread/${response.thread_id}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-[900px] flex-1 flex-col items-center justify-center gap-5 px-7">
      <h1 className="font-eyebrow text-xs uppercase tracking-wide text-[var(--mute)]">
        GenQL // New thread
      </h1>
      <form onSubmit={onSubmit} className="flex w-full flex-col gap-3">
        <Select value={datasource} onValueChange={(next) => setDatasource(next ?? '')}>
          <SelectTrigger className="w-full">
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
        <div className="flex items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2.5 pl-4">
          <input
            className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)]"
            placeholder="Ask a question about your data…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <Button type="submit" disabled={submitting || !datasource || !question.trim()}>
            {submitting ? 'Asking…' : 'Send'}
          </Button>
        </div>
      </form>
    </main>
  );
}
