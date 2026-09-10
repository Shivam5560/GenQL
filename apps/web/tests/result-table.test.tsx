import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResultTable } from '@/components/chat/result-table';
import type { TurnRecord } from '@/lib/types';

function turnWith(rows: unknown[][], columns = ['state', 'stores']): TurnRecord {
  return {
    turn_id: 't-1',
    sequence: 0,
    question: 'Which states have the most stores?',
    recap: null,
    validated_sql: 'select state, count(*) from stores group by state',
    clarifying_question: null,
    columns,
    rows,
    row_count: rows.length,
    applied_defaults: [],
    created_at: '2026-09-09T00:00:00Z',
  };
}

const STATES = ['CA', 'TX', 'FL', 'NY', 'IL', 'WA', 'GA', 'OH', 'PA', 'AZ', 'MI', 'NC'];
const BIG = STATES.map((state, index) => [state, 300 - index * 12]);

const table = (turn: TurnRecord) =>
  render(<ResultTable turn={turn} accessToken="test-token" threadId="t-thread" />);

describe('ResultTable', () => {
  it('previews the first five rows and says how many there are', () => {
    // The point of the cap: a 300-row answer used to push the SQL, the
    // question and the composer off the screen the moment it arrived.
    table(turnWith(BIG));

    expect(screen.getByText('CA')).toBeInTheDocument();
    expect(screen.getByText('IL')).toBeInTheDocument();
    expect(screen.queryByText('WA')).not.toBeInTheDocument();
    expect(screen.getByText('5 of 12 rows')).toBeInTheDocument();
  });

  it('shows the rest on request, and folds them away again', async () => {
    const user = userEvent.setup();
    table(turnWith(BIG));

    await user.click(screen.getByRole('button', { name: 'Show all 12' }));
    expect(screen.getByText('PA')).toBeInTheDocument();
    expect(screen.getByText('All 12 rows')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show first 5' }));
    expect(screen.queryByText('PA')).not.toBeInTheDocument();
  });

  it('offers no expander when everything already fits', () => {
    table(turnWith(BIG.slice(0, 3)));

    expect(screen.getByText('3 rows')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show all/i })).not.toBeInTheDocument();
  });

  it('says a query matched nothing instead of drawing an empty grid', () => {
    table(turnWith([]));

    expect(screen.getByText(/matched no rows/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('marks a null apart from a value rather than printing "null"', () => {
    table(turnWith([['CA', null]]));

    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('null')).not.toBeInTheDocument();
  });

  it('right-aligns a measure that arrives from the driver as a string', () => {
    // Numerics come back as strings from several drivers; testing typeof
    // alone would left-align half the measures in a result.
    table(turnWith([['CA', '284'], ['TX', '231']]));

    expect(screen.getByText('284').className).toContain('text-right');
    expect(screen.getByText('CA').className).toContain('text-left');
  });
});
