import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageTurn } from '@/components/chat/message-turn';
import type { TurnRecord } from '@/lib/types';

const EXECUTED_TURN: TurnRecord = {
  turn_id: 't-1',
  sequence: 0,
  question: 'What were total orders per region last quarter?',
  recap: 'Understood — total orders, grouped by region.',
  validated_sql: 'select region, count(*) from sales.orders group by region;',
  clarifying_question: null,
  columns: ['region', 'orders'],
  rows: [['NA', 4812]],
  row_count: 1,
  applied_defaults: [],
  created_at: '2026-09-09T00:00:00Z',
};

describe('MessageTurn', () => {
  it('does not render a result table before the query is run', () => {
    render(
      <MessageTurn
        turn={EXECUTED_TURN}
        revealed={false}
        onReveal={() => {}}
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    expect(screen.queryByText('NA')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run query/i })).toBeInTheDocument();
  });

  it('reveals the result table and feedback controls only after the query is run', async () => {
    const user = userEvent.setup();
    let revealed = false;
    const { rerender } = render(
      <MessageTurn
        turn={EXECUTED_TURN}
        revealed={revealed}
        onReveal={() => {
          revealed = true;
        }}
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    await user.click(screen.getByRole('button', { name: /run query/i }));

    await waitFor(() => expect(revealed).toBe(true));
    rerender(
      <MessageTurn
        turn={EXECUTED_TURN}
        revealed={revealed}
        onReveal={() => {}}
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    expect(screen.getByText('NA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^yes$/i })).toBeInTheDocument();
  });

  it('switching the dialect selector updates its displayed value', async () => {
    const user = userEvent.setup();
    render(
      <MessageTurn
        turn={EXECUTED_TURN}
        revealed
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'Snowflake' }));

    expect(screen.getByRole('combobox')).toHaveTextContent('Snowflake');
  });
});
