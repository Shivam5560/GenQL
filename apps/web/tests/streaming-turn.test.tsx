import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PendingTurn } from '@/components/chat/pending-turn';
import { buildRows, StageRail } from '@/components/chat/stage-rail';
import { streamTurn } from '@/lib/api-client';
import type { PendingTurn as PendingTurnState, StageEvent } from '@/lib/types';

function stubStream(frames: string[]) {
  const encoder = new TextEncoder();
  return (): Promise<Response> => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      },
    });
    return Promise.resolve({ ok: true, status: 200, body: stream } as unknown as Response);
  };
}

const pending = (over: Partial<PendingTurnState> = {}): PendingTurnState => ({
  localId: 'p-1',
  question: 'Revenue by region last quarter',
  stages: [],
  startedAt: Date.now(),
  error: null,
  ...over,
});

describe('PendingTurn', () => {
  it('shows the question immediately, before any stage has reported', () => {
    render(<PendingTurn turn={pending()} onRetry={() => {}} />);

    expect(screen.getByText('Revenue by region last quarter')).toBeInTheDocument();
  });

  it('reports progress without putting the pipeline transcript in the thread', () => {
    // Stage summaries belong in the rail, which keeps them in order. Printing
    // the newest one here made them flicker through the conversation and
    // vanish, so the transcript said something different every second and
    // retained none of it.
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '7 objects linked' },
      { stage: 'candidate_generation', status: 'completed', detail: '4 candidates generated' },
    ];

    render(<PendingTurn turn={pending({ stages })} onRetry={() => {}} />);

    expect(screen.queryByText('4 candidates generated')).not.toBeInTheDocument();
    expect(screen.getByText(/2 stages done/)).toBeInTheDocument();
  });

  it('offers a way out of a turn that is taking too long', () => {
    const onStop = vi.fn();

    render(<PendingTurn turn={pending()} onRetry={() => {}} onStop={onStop} />);

    screen.getByRole('button', { name: /stop/i }).click();
    expect(onStop).toHaveBeenCalled();
  });

  it('keeps the question on screen when the turn fails, and offers a retry', async () => {
    const onRetry = vi.fn();
    const error = { error: 'StaticValidationError', detail: 'Every candidate was rejected.' };

    render(<PendingTurn turn={pending({ error })} onRetry={onRetry} />);

    expect(screen.getByText('Revenue by region last quarter')).toBeInTheDocument();
    // Spaced, not camel-cased: the heading is read, not parsed.
    expect(screen.getByRole('alert')).toHaveTextContent('Static Validation Error');
    expect(screen.getByRole('alert')).toHaveTextContent('Every candidate was rejected.');
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('folds a driver stack away and leads with what to do about it', () => {
    // A psycopg error runs to fifteen lines — the SQLSTATE name, the offending
    // line, a caret, the whole statement and a docs URL — and it used to sit
    // above the one sentence saying what to do, dwarfing it.
    const error = {
      error: 'CostEstimationError',
      detail:
        'EXPLAIN failed: (psycopg.errors.UndefinedParameter) there is no parameter $1 LINE 1: ' +
        '...hd.hd_demo_sk AND hd.hd_income_band_sk = ANY(CAST($1 AS INT[... ^ [SQL: EXPLAIN ' +
        '(FORMAT JSON) SELECT DISTINCT c.c_customer_sk FROM tpcds.store_sales AS ss WHERE TRUE ' +
        'LIMIT 100] (Background on this error at: https://sqlalche.me/e/20/f405)',
    };

    render(<PendingTurn turn={pending({ error })} onRetry={() => {}} />);

    expect(screen.getByText(/placeholder for a value that was never decided/)).toBeInTheDocument();
    expect(screen.getByText(/Show technical detail/)).toBeInTheDocument();
  });
});

describe('StageRail', () => {
  it('lists every pipeline stage, with the newest report open beside it', () => {
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '7 objects linked' },
    ];

    render(<StageRail stages={stages} running startedAt={Date.now()} />);

    expect(screen.getByText('Schema linking')).toBeInTheDocument();
    // Only one stage's "why" is expanded at a time; live, it is the newest
    // one to have reported, so there is something to read without clicking.
    expect(screen.getByText('7 objects linked')).toBeVisible();
    // The stages that have not run yet are still listed, so the rail reads as
    // a pipeline rather than as a growing log.
    expect(screen.getByText('Execution')).toBeInTheDocument();
  });

  it('keeps every stage but the open one collapsed, and swaps on a click', async () => {
    // The rail used to print every detail at once — twelve rows of two lines
    // in a 240px column, which is a paragraph dump rather than a discussion.
    // One open at a time is what makes it something you page through.
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '7 objects linked' },
      { stage: 'candidate_selection', status: 'completed', detail: 'selected by critique severity' },
    ];

    render(<StageRail stages={stages} running={false} startedAt={null} />);

    expect(screen.getByText('selected by critique severity')).toBeVisible();
    expect(screen.getByText('7 objects linked')).not.toBeVisible();

    screen.getByRole('button', { name: 'Schema linking' }).click();

    await waitFor(() => expect(screen.getByText('7 objects linked')).toBeVisible());
    expect(screen.getByText('selected by critique severity')).not.toBeVisible();
  });

  it('offers no disclosure on a stage that reported nothing', () => {
    // A stage with no detail still lists — that it ran is the useful part —
    // but pressing it would open an empty panel, so it is not pressable.
    render(
      <StageRail
        stages={[{ stage: 'planning', status: 'completed', detail: null }]}
        running={false}
        startedAt={null}
      />,
    );

    expect(screen.getByText('Planning')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Planning' })).not.toBeInTheDocument();
  });

  it('shows a stage the client has never heard of rather than dropping it', () => {
    // stage_events.py is open/closed by design: a node added later streams
    // without anyone editing the client, and must not be invisible here.
    const stages: StageEvent[] = [
      { stage: 'semantic_reranking', status: 'completed', detail: '12 reranked' },
    ];

    render(<StageRail stages={stages} running={false} startedAt={null} />);

    expect(screen.getByText('Semantic reranking')).toBeInTheDocument();
    expect(screen.getByText('12 reranked')).toBeVisible();
  });

  it('lists what happened in the order it happened, ahead of what has not', () => {
    // The old rail rendered a fixed skeleton and appended anything it did not
    // recognise at the bottom — so a stage that ran second appeared last, and
    // the rail read as a false account of the turn.
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: null },
      { stage: 'semantic_reranking', status: 'completed', detail: null },
      { stage: 'planning', status: 'completed', detail: null },
    ];

    expect(buildRows(stages, false).map((row) => row.label).slice(0, 3)).toEqual([
      'Schema linking',
      'Semantic reranking',
      'Planning',
    ]);
  });

  it('does not list a stage twice when the gate runs another round', () => {
    const stages: StageEvent[] = [
      { stage: 'ambiguity_gate', status: 'paused', detail: 'What period?' },
      { stage: 'ambiguity_gate', status: 'completed', detail: null },
    ];

    const gateRows = buildRows(stages, false).filter((row) => row.key === 'ambiguity_gate');

    expect(gateRows).toHaveLength(1);
    expect(gateRows[0].state).toBe('done');
  });

  it('marks only the next unreported stage as running', () => {
    const rows = buildRows([{ stage: 'intent_classification', status: 'completed', detail: null }], true);

    expect(rows.filter((row) => row.state === 'running')).toHaveLength(1);
  });

  it('keeps a stage the pipeline skipped apart from one that finished', () => {
    // Critique and probing short-circuit on an uncontested turn. Folding
    // `skipped` into `done` puts a green tick beside work that never ran —
    // and it is the same conflation that used to sort three stages which had
    // genuinely run below stages that had not.
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '9 objects linked' },
      { stage: 'critique', status: 'skipped', detail: 'not contested' },
    ];

    const rows = buildRows(stages, false);

    expect(rows.find((row) => row.key === 'schema_linking')?.state).toBe('done');
    expect(rows.find((row) => row.key === 'critique')?.state).toBe('skipped');
  });
});

describe('streamTurn', () => {
  it('reports each stage as it arrives, then the terminal result', async () => {
    const original = globalThis.fetch;
    globalThis.fetch = stubStream([
      'event: stage\ndata: {"stage":"planning","status":"completed","detail":"planned"}\n\n',
      'event: result\ndata: {"thread_id":"t-1","validated_sql":"SELECT 1"}\n\n',
    ]) as typeof fetch;

    const stages: StageEvent[] = [];
    const onTerminal = vi.fn();
    const onError = vi.fn();

    try {
      await streamTurn(
        'token',
        { question: 'q', datasource: 'warehouse' },
        { onStage: (s) => stages.push(s), onTerminal, onError },
      );
    } finally {
      globalThis.fetch = original;
    }

    expect(stages.map((s) => s.stage)).toEqual(['planning']);
    expect(onTerminal).toHaveBeenCalledWith(
      expect.objectContaining({ thread_id: 't-1', validated_sql: 'SELECT 1' }),
    );
    expect(onError).not.toHaveBeenCalled();
  });

  it('surfaces a typed pipeline failure instead of a generic message', async () => {
    const original = globalThis.fetch;
    globalThis.fetch = stubStream([
      'event: error\ndata: {"error":"CostEstimationError","detail":"over budget"}\n\n',
    ]) as typeof fetch;

    const onError = vi.fn();
    try {
      await streamTurn(
        'token',
        { question: 'q', datasource: 'warehouse' },
        { onStage: () => {}, onTerminal: () => {}, onError },
      );
    } finally {
      globalThis.fetch = original;
    }

    expect(onError).toHaveBeenCalledWith({ error: 'CostEstimationError', detail: 'over budget' });
  });

  it('reports a dropped connection through the same error path', async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (() => Promise.reject(new TypeError('network down'))) as typeof fetch;

    const onError = vi.fn();
    try {
      await streamTurn(
        'token',
        { question: 'q', datasource: 'warehouse' },
        { onStage: () => {}, onTerminal: () => {}, onError },
      );
    } finally {
      globalThis.fetch = original;
    }

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ error: 'ConnectionError' }),
      ),
    );
  });

  it('keeps a serialized payload out of the rail', () => {
    // The ambiguity gate reports its whole payload, which arrives as a Python
    // dict repr and filled the 212px rail with quoted keys restating a
    // question already on screen in full. The stage still lists; the blob
    // does not.
    const stages: StageEvent[] = [
      {
        stage: 'ambiguity_gate',
        status: 'paused',
        detail:
          "{'question': 'What time range should the sales totals cover?', " +
          "'suggested_answer': 'all available history'}",
      },
    ];

    render(<StageRail stages={stages} running={false} startedAt={null} />);

    expect(screen.getByText('Ambiguity gate')).toBeInTheDocument();
    expect(screen.queryByText(/suggested_answer/)).not.toBeInTheDocument();
  });

  it('still shows a plain-prose detail', () => {
    render(
      <StageRail
        stages={[{ stage: 'candidate_generation', status: 'completed', detail: '4 candidates' }]}
        running={false}
        startedAt={null}
      />,
    );

    expect(screen.getByText('4 candidates')).toBeInTheDocument();
  });
});
