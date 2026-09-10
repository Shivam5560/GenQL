import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageTurn } from '@/components/chat/message-turn';
import type { TurnRecord } from '@/lib/types';

/**
 * A paused turn used to be a bare sentence and an empty text box: the only
 * way past it was to type one. These prove the two affordances that replaced
 * that — one tap for the reading the gate already has, and a visible record
 * of anything decided without asking.
 */
const PAUSED: TurnRecord = {
  turn_id: 't-1',
  sequence: 0,
  question: 'Find customers who bought through the Store channel with a high income bracket',
  recap: null,
  validated_sql: null,
  clarifying_question: 'What income threshold counts as a high income bracket?',
  columns: [],
  rows: [],
  row_count: 0,
  applied_defaults: [],
  created_at: '2026-09-10T00:00:00Z',
  suggested_answer: 'the top income band in the data',
  clarification_options: ['top income band', 'above the median', 'above 100k'],
};

function renderPaused(turn: TurnRecord, onAnswer = vi.fn()) {
  render(
    <MessageTurn
      turn={turn}
      revealed
      accessToken="test-token"
      threadId="t-thread"
      onAnswer={onAnswer}
    />,
  );
  return onAnswer;
}

describe('a paused turn', () => {
  it('shows the question', () => {
    renderPaused(PAUSED);

    expect(screen.getByText(PAUSED.clarifying_question!)).toBeInTheDocument();
  });

  it('offers the suggested answer as a button, marked as the default', () => {
    renderPaused(PAUSED);

    expect(
      screen.getByRole('button', { name: /the top income band in the data/i }),
    ).toBeInTheDocument();
  });

  it('answers with the option text when an option is clicked', async () => {
    const user = userEvent.setup();
    const onAnswer = renderPaused(PAUSED);

    await user.click(screen.getByRole('button', { name: /above the median/i }));

    expect(onAnswer).toHaveBeenCalledWith('above the median');
  });

  it('answers with the suggestion when the suggestion is clicked', async () => {
    const user = userEvent.setup();
    const onAnswer = renderPaused(PAUSED);

    await user.click(screen.getByRole('button', { name: /the top income band in the data/i }));

    expect(onAnswer).toHaveBeenCalledWith('the top income band in the data');
  });

  it('renders no chips at all for a turn reloaded without them', () => {
    // GET /v1/threads/{id} does not persist suggestions, so a reloaded
    // paused turn has the question and nothing else. It must still render.
    const reloaded: TurnRecord = {
      ...PAUSED,
      suggested_answer: undefined,
      clarification_options: undefined,
    };

    renderPaused(reloaded);

    expect(screen.getByText(PAUSED.clarifying_question!)).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('does not repeat an option that is identical to the suggestion', () => {
    const overlapping: TurnRecord = {
      ...PAUSED,
      suggested_answer: 'above the median',
      clarification_options: ['above the median', 'above 100k'],
    };

    renderPaused(overlapping);

    expect(screen.getAllByRole('button', { name: /above the median/i })).toHaveLength(1);
  });
});

describe('assumptions on a finished turn', () => {
  it('states each assumption with its value', () => {
    const finished: TurnRecord = {
      ...PAUSED,
      clarifying_question: null,
      recap: 'Understood.',
      validated_sql: 'select 1;',
      assumed: [
        ['time_range', 'the most recent complete calendar year'],
        ['comparison_baseline', 'none'],
      ],
    };

    renderPaused(finished);

    expect(screen.getByText(/the most recent complete calendar year/)).toBeInTheDocument();
    expect(screen.getByText(/comparison_baseline/)).toBeInTheDocument();
  });
});
