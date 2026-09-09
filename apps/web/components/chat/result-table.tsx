import type { TurnRecord } from '@/lib/types';
import { FeedbackRow } from './feedback-row';

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
        <span className="font-eyebrow text-[0.68rem] text-[var(--mute)]">{turn.row_count} rows</span>
        <FeedbackRow accessToken={accessToken} threadId={threadId} />
      </div>
    </div>
  );
}
