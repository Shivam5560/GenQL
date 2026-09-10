'use client';

import { Fragment, useState } from 'react';
import { formatDuration, glanceOf } from './stage-glance';
import type { PhaseKey, Row, RowState } from './stage-rows';
import { defaultOpenKey, isExpandable, phaseLabel } from './stage-rows';

/**
 * The turn's trail: one line per stage, grouped by what the pipeline was doing.
 *
 * The rail used to print every stage's label and every stage's detail at once —
 * twelve rows of two lines each in a 240px column, a paragraph dump you
 * scrolled past rather than read. Then it became a numbered line you paged
 * through, which fixed the dump and introduced an ordinal nobody could use:
 * "stage 7" means nothing, and the numbers renumbered themselves whenever the
 * pipeline skipped something.
 *
 * Here each row carries the one value it is about — "3 cleared", "top 0.92" —
 * so the trail is readable without opening anything, and opening a row shows
 * the sentence plus every fact the stage reported. Headings mark where the
 * phase changes; rows stay in arrival order, so a stage that ran second is
 * still never drawn last.
 */
function markColour(state: RowState): string {
  if (state === 'done') return 'bg-[var(--ok)]';
  if (state === 'failed') return 'bg-[var(--bad)]';
  if (state === 'running' || state === 'paused') return 'bg-[var(--brand)]';
  return 'bg-[var(--line)]';
}

/** A filled dot for work that happened, a bar for work that did not. */
function Mark({ state }: { state: RowState }) {
  if (state === 'skipped' || state === 'waiting') {
    return (
      <span
        aria-hidden
        className={`h-px w-2 shrink-0 ${
          state === 'skipped' ? 'bg-[var(--mute)]' : 'bg-[var(--line)]'
        }`}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={`size-2 shrink-0 rounded-full ${markColour(state)} ${
        state === 'running' ? 'gq-pulse' : ''
      }`}
    />
  );
}

function stateLabel(state: RowState): string | null {
  if (state === 'running') return 'in progress';
  if (state === 'failed') return 'stopped here';
  if (state === 'paused') return 'asked you a question';
  return null;
}

function labelTone(state: RowState): string {
  if (state === 'waiting') return 'text-[var(--mute)] opacity-55';
  if (state === 'skipped') return 'text-[var(--mute)]';
  return 'text-[var(--ink)]';
}

/** Everything a stage reported, shown once its row is opened. */
function Panel({ row, open }: { row: Row; open: boolean }) {
  const duration = formatDuration(row.durationMs);
  return (
    <div
      className="gq-stage-panel"
      // Inline as well as in the class, so a collapsed panel is genuinely
      // hidden rather than merely zero-height: a detail nobody can see must not
      // be reachable by find-in-page, by a screen reader, or by a test that
      // thinks it is on screen.
      style={{ gridTemplateRows: open ? '1fr' : '0fr', visibility: open ? 'visible' : 'hidden' }}
      data-open={open}
    >
      <div className="overflow-hidden">
        {/* The sentence only when there are no facts. A summariser builds its
            detail out of the same values it reports as facts, so showing both
            prints "100 rows" directly above "ROWS 100". Facts are the richer
            of the two; the sentence is what a trail recorded before they
            existed has instead of them. */}
        {row.facts.length === 0 && row.detail && (
          <p className="mt-1 break-words text-[0.72rem] leading-snug text-[var(--mute)]">
            {row.detail}
          </p>
        )}
        {row.facts.length > 0 && (
          <dl className="mt-1.5 flex flex-col gap-1">
            {row.facts.map(([label, value]) => (
              <div key={label} className="flex gap-2">
                <dt className="w-[5.4rem] shrink-0 font-mono text-[0.58rem] uppercase leading-relaxed tracking-[0.08em] text-[var(--mute)] opacity-70">
                  {label}
                </dt>
                <dd className="min-w-0 break-words text-[0.7rem] leading-relaxed text-[var(--ink)]">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {duration && (
          <p className="mt-1.5 font-mono text-[0.58rem] tabular-nums text-[var(--mute)] opacity-60">
            took {duration}
          </p>
        )}
      </div>
    </div>
  );
}

function TrailRow({
  row,
  open,
  onToggle,
}: {
  row: Row;
  open: boolean;
  onToggle: () => void;
}) {
  const state = stateLabel(row.state);
  const glance = glanceOf(row);

  // `aria-hidden` on everything but the label, so the button's accessible name
  // stays the stage's name — what a reader hears, and what a test asks for.
  const line = (
    <>
      <Mark state={row.state} />
      <span className={`truncate text-[0.76rem] leading-tight ${labelTone(row.state)}`}>
        {row.label}
        {state && <span className="ml-1 text-[var(--mute)]">— {state}</span>}
      </span>
      {glance && (
        <span
          aria-hidden
          className="ml-auto shrink-0 truncate pl-2 font-mono text-[0.6rem] tabular-nums text-[var(--mute)]"
        >
          {glance}
        </span>
      )}
      {row.attempt > 1 && (
        <span aria-hidden className="shrink-0 font-mono text-[0.55rem] text-[var(--brand)]">
          ·{row.attempt}
        </span>
      )}
    </>
  );

  return (
    <li className="flex flex-col">
      {isExpandable(row) ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={onToggle}
          className="flex w-full cursor-pointer items-center gap-2 py-[3px] text-left transition-colors hover:text-[var(--brand)]"
        >
          {line}
        </button>
      ) : (
        <p className="flex items-center gap-2 py-[3px]">{line}</p>
      )}
      {isExpandable(row) && <Panel row={row} open={open} />}
    </li>
  );
}

/** A heading wherever the phase changes, with what that stretch cost. */
function phaseBreaks(rows: Row[]): Map<number, { phase: PhaseKey; ms: number | null }> {
  const breaks = new Map<number, { phase: PhaseKey; ms: number | null }>();
  rows.forEach((row, index) => {
    if (index > 0 && rows[index - 1].phase === row.phase) return;
    let ms: number | null = null;
    for (let ahead = index; ahead < rows.length && rows[ahead].phase === row.phase; ahead += 1) {
      if (rows[ahead].durationMs !== null) ms = (ms ?? 0) + (rows[ahead].durationMs ?? 0);
    }
    breaks.set(index, { phase: row.phase, ms });
  });
  return breaks;
}

export function StageTimeline({ rows, trailKey }: { rows: Row[]; trailKey: string }) {
  // Until someone clicks, the open row is derived rather than stored, so it
  // follows the pipeline down as a live turn reports. After a click it is
  // theirs: a stage arriving a second later must not snatch the panel back.
  // The choice is stamped with the trail it was made on, so pointing the rail
  // at a different turn falls back to that turn's default without an effect
  // that resets state after the fact.
  const [chosen, setChosen] = useState<{ trail: string; key: string | null } | null>(null);
  const key = chosen?.trail === trailKey ? chosen.key : defaultOpenKey(rows);
  const breaks = phaseBreaks(rows);

  return (
    // No scroll container of its own. The rail has exactly one scrolling
    // region — the column holding the decisions and this trail — and a second
    // one nested inside it traps the wheel: you reach the end of the trail and
    // the panel behind it refuses to move.
    <ol className="flex flex-col">
      {rows.map((row, index) => {
        const heading = breaks.get(index);
        const open = row.key === key;
        return (
          // A fragment, not a wrapper element: the heading and the row are both
          // children of the <ol>, and an <li> nested inside an <li> is neither
          // valid nor what a screen reader should be handed.
          <Fragment key={row.key}>
            {heading && (
              <li className="flex items-baseline gap-2 pb-1 pt-3 first:pt-0">
                <span className="font-eyebrow text-[0.58rem] uppercase tracking-[0.16em] text-[var(--mute)] opacity-60">
                  {phaseLabel(heading.phase)}
                </span>
                {formatDuration(heading.ms) && (
                  <span className="ml-auto font-mono text-[0.58rem] tabular-nums text-[var(--mute)] opacity-60">
                    {formatDuration(heading.ms)}
                  </span>
                )}
              </li>
            )}
            <TrailRow
              row={row}
              open={open}
              onToggle={() =>
                // Accordion: opening one closes the rest, and pressing the open
                // one closes it, so the trail can be read as bare labels.
                setChosen({ trail: trailKey, key: open ? null : row.key })
              }
            />
          </Fragment>
        );
      })}
    </ol>
  );
}
