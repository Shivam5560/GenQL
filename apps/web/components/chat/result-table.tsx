'use client';

import { useState } from 'react';
import type { TurnRecord } from '@/lib/types';
import { FeedbackRow } from './feedback-row';

/**
 * How many rows a result shows before it asks.
 *
 * Executing used to print every returned row, so a question that answered
 * with three hundred took over the screen: the SQL you were checking scrolled
 * away, the question above it scrolled away, and the follow-up composer was a
 * flick of the wheel below the fold. Eight rows is enough to see the shape of
 * an answer — the top of a ranking, whether the units look right, whether
 * anything is null — and everything past that is either a scroll away or a
 * spreadsheet away.
 */
const PREVIEW_ROWS = 8;

function csvEscape(value: unknown): string {
  const str = value === null || value === undefined ? '' : String(value);
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function downloadCsv(turn: TurnRecord) {
  const lines = [
    turn.columns.map(csvEscape).join(','),
    ...turn.rows.map((row) => row.map(csvEscape).join(',')),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `genql-results-${turn.turn_id}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * True when every value present in a column is a number.
 *
 * Warehouse drivers hand back numerics as strings often enough that testing
 * the JavaScript type alone would left-align half the measures in a result.
 * Nulls do not vote: a column of counts with one gap is still a column of
 * counts.
 */
function isNumericColumn(rows: unknown[][], index: number): boolean {
  let seen = 0;
  for (const row of rows) {
    const cell = row[index];
    if (cell === null || cell === undefined || cell === '') continue;
    if (typeof cell === 'number') {
      seen += 1;
      continue;
    }
    if (typeof cell === 'string' && cell.trim() !== '' && Number.isFinite(Number(cell))) {
      seen += 1;
      continue;
    }
    return false;
  }
  return seen > 0;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function ResultTable({
  turn,
  accessToken,
  threadId,
}: {
  turn: TurnRecord;
  accessToken: string;
  threadId: string;
}) {
  const [expanded, setExpanded] = useState(false);

  const total = turn.rows.length;
  const hidden = Math.max(total - PREVIEW_ROWS, 0);
  const visible = expanded ? turn.rows : turn.rows.slice(0, PREVIEW_ROWS);
  const numeric = turn.columns.map((_, index) => isNumericColumn(turn.rows, index));

  if (total === 0) {
    return (
      <div className="border-t border-[var(--line)] px-4 py-6">
        <p className="text-sm text-[var(--mute)]">
          The query ran and matched no rows. Widen the filters in a follow-up to see why.
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-[var(--line)]">
      {/* Expanded, the rows scroll inside this box rather than pushing the
          page — so the question and the SQL stay exactly where they were and
          the composer never leaves the screen. */}
      <div className={`overflow-x-auto ${expanded ? 'max-h-[26rem] overflow-y-auto' : ''}`}>
        {/* `w-auto min-w-full` plus the trailing spacer column below: columns
            size to their own content and the leftover width collects at the
            right, instead of two columns being stretched to opposite edges of
            the card with a void between a header and its numbers. */}
        <table className="w-auto min-w-full border-collapse text-[0.8rem]">
          <thead className="sticky top-0 z-10 bg-[var(--panel)]">
            <tr>
              <th
                scope="col"
                className="border-b border-[var(--line)] py-2 pl-4 pr-1 text-right text-[0.68rem] font-medium text-[var(--mute)]"
              >
                <span className="sr-only">Row</span>
              </th>
              {turn.columns.map((column, index) => (
                <th
                  key={column}
                  scope="col"
                  className={`whitespace-nowrap border-b border-[var(--line)] px-3.5 py-2 text-[0.72rem] font-semibold text-[var(--mute)] ${
                    numeric[index] ? 'text-right' : 'text-left'
                  }`}
                >
                  {column}
                </th>
              ))}
              <th aria-hidden className="w-full border-b border-[var(--line)]" />
            </tr>
          </thead>
          <tbody>
            {visible.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-[var(--line)] last:border-0">
                <td className="py-2 pl-4 pr-1 text-right font-mono text-[0.68rem] text-[var(--mute)] [font-variant-numeric:tabular-nums]">
                  {rowIndex + 1}
                </td>
                {row.map((cell, cellIndex) => {
                  const empty = cell === null || cell === undefined;
                  return (
                    <td
                      key={cellIndex}
                      className={`px-3.5 py-2 font-mono [font-variant-numeric:tabular-nums] ${
                        numeric[cellIndex] ? 'text-right' : 'text-left'
                      } ${empty ? 'text-[var(--mute)]' : ''}`}
                    >
                      {formatCell(cell)}
                    </td>
                  );
                })}
                <td aria-hidden />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] bg-[var(--panel-2)] px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* The count states what is on screen and what exists, because those
              are two different numbers and the difference is the whole reason
              there is a button next to it. */}
          <span className="font-eyebrow text-[0.62rem] uppercase tracking-[0.1em] text-[var(--mute)]">
            {hidden === 0
              ? `${total} ${total === 1 ? 'row' : 'rows'}`
              : expanded
                ? `All ${total} rows`
                : `${PREVIEW_ROWS} of ${total} rows`}
          </span>
          {hidden > 0 && (
            <button
              type="button"
              onClick={() => setExpanded((open) => !open)}
              className="rounded border border-[var(--line)] px-2.5 py-1 font-eyebrow text-[0.62rem] uppercase tracking-[0.1em] text-[var(--ink)]"
            >
              {expanded ? 'Show first 8' : `Show all ${total}`}
            </button>
          )}
          <button
            type="button"
            className="rounded border border-[var(--line)] px-2.5 py-1 font-eyebrow text-[0.62rem] uppercase tracking-[0.1em] text-[var(--mute)]"
            onClick={() => downloadCsv(turn)}
          >
            Download CSV
          </button>
        </div>
        <FeedbackRow accessToken={accessToken} threadId={threadId} />
      </div>
    </div>
  );
}
