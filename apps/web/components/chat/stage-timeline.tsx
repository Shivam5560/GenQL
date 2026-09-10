'use client';

import { useState } from 'react';
import type { Row, RowState } from './stage-rows';
import { defaultOpenKey } from './stage-rows';

/**
 * The turn's discussion, drawn as a line you read down rather than a list.
 *
 * The rail used to print every stage's label and every stage's detail at once:
 * twelve rows of two lines each, a paragraph dump in a 240px column that you
 * scrolled past rather than read. Here each stage is a numbered node on one
 * connecting line, and only one node's "why" is open at a time — so the panel
 * is a story you page through, and its height stays the same whether a turn
 * ran four stages or twelve.
 *
 * A stage that reported nothing is not expandable. There is no disclosure to
 * press and no empty panel under it: it lists its label and its state, which
 * is all the pipeline said about it, and the eye moves on.
 */
function nodeColour(state: RowState): string {
  if (state === 'done') return 'bg-[var(--ok)]';
  if (state === 'failed') return 'bg-[var(--bad)]';
  if (state === 'running' || state === 'paused') return 'bg-[var(--brand)]';
  return 'bg-[var(--line)]';
}

/** The numbered node itself: a filled circle sitting on the line. */
function Node({ state, index }: { state: RowState; index: number }) {
  const waiting = state === 'waiting';
  return (
    <span
      aria-hidden
      className={`absolute left-0 top-[0.1rem] grid size-[15px] place-items-center rounded-full font-mono text-[0.5rem] leading-none tabular-nums ${nodeColour(
        state,
      )} ${waiting ? 'text-[var(--mute)] opacity-60' : 'text-[var(--panel-2)]'} ${
        state === 'running' ? 'gq-pulse' : ''
      }`}
    >
      {index + 1}
    </span>
  );
}

function stateLabel(state: RowState): string | null {
  if (state === 'running') return 'in progress';
  if (state === 'failed') return 'stopped here';
  if (state === 'paused') return 'asked you a question';
  return null;
}

export function StageTimeline({ rows, trailKey }: { rows: Row[]; trailKey: string }) {
  // Until someone clicks, the open stage is derived rather than stored, so it
  // follows the pipeline down the line as a live turn reports. After a click
  // it is theirs: a stage arriving a second later must not snatch the panel
  // back. The choice is stamped with the trail it was made on, so pointing the
  // rail at a different turn falls back to that turn's default without an
  // effect that resets state after the fact.
  const [chosen, setChosen] = useState<{ trail: string; key: string | null } | null>(null);
  const key = chosen?.trail === trailKey ? chosen.key : defaultOpenKey(rows);

  return (
    <ol className="relative flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto py-0.5 pr-1">
      {/* One line down the left edge, behind the nodes. Inset top and bottom
          so it reads as connecting the stages rather than as a border on the
          scroll container. */}
      <span
        aria-hidden
        className="pointer-events-none absolute bottom-2 left-[7px] top-2 w-px bg-[var(--line)]"
      />
      {rows.map((row, index) => {
        const open = row.key === key;
        const state = stateLabel(row.state);
        return (
          <li key={row.key} className="relative pl-[1.4rem]">
            <Node state={row.state} index={index} />
            {row.detail ? (
              <button
                type="button"
                aria-expanded={open}
                onClick={() =>
                  // Accordion: opening one closes the rest, and pressing the
                  // open one closes it, so the rail can be read as bare labels.
                  setChosen({ trail: trailKey, key: open ? null : row.key })
                }
                className="w-full cursor-pointer text-left text-[0.76rem] leading-tight text-[var(--ink)] transition-colors hover:text-[var(--brand)]"
              >
                {row.label}
                {state && <span className="ml-1 text-[var(--mute)]">— {state}</span>}
              </button>
            ) : (
              <p
                className={`text-[0.76rem] leading-tight ${
                  row.state === 'waiting' ? 'text-[var(--mute)] opacity-55' : 'text-[var(--ink)]'
                }`}
              >
                {row.label}
                {state && <span className="ml-1 text-[var(--mute)]">— {state}</span>}
              </p>
            )}
            {row.detail && (
              <div
                className="gq-stage-panel"
                data-open={open}
                // Inline, not only in the class, so the collapsed panel is
                // genuinely hidden rather than merely zero-height: a detail
                // nobody can see must not be reachable by find-in-page, by a
                // screen reader, or by a test that thinks it is on screen.
                style={{
                  gridTemplateRows: open ? '1fr' : '0fr',
                  visibility: open ? 'visible' : 'hidden',
                }}
              >
                <div className="overflow-hidden">
                  <p className="mt-1 break-words font-mono text-[0.68rem] leading-snug text-[var(--mute)]">
                    {row.detail}
                  </p>
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
