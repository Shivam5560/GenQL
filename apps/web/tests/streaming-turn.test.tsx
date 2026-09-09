import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PendingTurn } from '@/components/chat/pending-turn';
import { StageRail } from '@/components/chat/stage-rail';
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

  it("reports the latest stage's own summary rather than a generic spinner", () => {
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '7 objects linked' },
      { stage: 'candidate_generation', status: 'completed', detail: '4 candidates generated' },
    ];

    render(<PendingTurn turn={pending({ stages })} onRetry={() => {}} />);

    expect(screen.getByText('4 candidates generated')).toBeInTheDocument();
  });

  it('keeps the question on screen when the turn fails, and offers a retry', async () => {
    const onRetry = vi.fn();
    const error = { error: 'StaticValidationError', detail: 'Every candidate was rejected.' };

    render(<PendingTurn turn={pending({ error })} onRetry={onRetry} />);

    expect(screen.getByText('Revenue by region last quarter')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('StaticValidationError');
    expect(screen.getByRole('alert')).toHaveTextContent('Every candidate was rejected.');
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});

describe('StageRail', () => {
  it('lists every pipeline stage, with the reported counts beside them', () => {
    const stages: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '7 objects linked' },
    ];

    render(<StageRail stages={stages} running startedAt={Date.now()} />);

    expect(screen.getByText('Schema linking')).toBeInTheDocument();
    expect(screen.getByText('7 objects linked')).toBeInTheDocument();
    // The stages that have not run yet are still listed, so the rail reads as
    // a pipeline rather than as a growing log.
    expect(screen.getByText('Execution')).toBeInTheDocument();
  });

  it('shows a stage the client has never heard of rather than dropping it', () => {
    // stage_events.py is open/closed by design: a node added later streams
    // without anyone editing the client, and must not be invisible here.
    const stages: StageEvent[] = [
      { stage: 'semantic_reranking', status: 'completed', detail: '12 reranked' },
    ];

    render(<StageRail stages={stages} running={false} startedAt={null} />);

    expect(screen.getByText('Semantic reranking')).toBeInTheDocument();
    expect(screen.getByText('12 reranked')).toBeInTheDocument();
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
});
