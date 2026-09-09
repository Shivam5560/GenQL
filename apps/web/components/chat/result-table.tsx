import type { TurnRecord } from '@/lib/types';
import { FeedbackRow } from './feedback-row';

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

export function ResultTable({
  turn,
  accessToken,
  threadId,
}: {
  turn: TurnRecord;
  accessToken: string;
  threadId: string;
}) {
  return (
    <div className="overflow-hidden rounded-b-md border-t border-[var(--line)]">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
          <thead>
            <tr>
              {turn.columns.map((column) => (
                <th
                  key={column}
                  className="font-sans border-b border-[var(--line)] px-3.5 py-2 text-left text-[0.68rem] font-semibold uppercase tracking-wide text-[var(--mute)]"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {turn.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-b border-[var(--line)] px-3.5 py-2 last:border-0">
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-[var(--line)] bg-[var(--panel-2)] px-3.5 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="font-eyebrow text-[0.68rem] text-[var(--mute)]">{turn.row_count} rows</span>
          <button
            className="font-eyebrow rounded border border-[var(--line)] px-2 py-1 text-[0.68rem] uppercase text-[var(--mute)]"
            onClick={() => downloadCsv(turn)}
          >
            Export CSV
          </button>
        </div>
        <FeedbackRow accessToken={accessToken} threadId={threadId} />
      </div>
    </div>
  );
}
