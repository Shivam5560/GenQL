import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { StageRail } from '@/components/chat/stage-rail';
import { buildDecisions } from '@/components/chat/stage-decisions';
import { buildRows } from '@/components/chat/stage-rows';
import { glanceOf } from '@/components/chat/stage-glance';
import type { StageEvent } from '@/lib/types';

/**
 * The rail reads in two tiers: what was decided, then what was done. Both are
 * built from `StageEvent.facts` and nothing else — no field the backend does
 * not send is displayed, and no card is drawn for a decision that was not made.
 */
const stage = (
  name: string,
  facts: [string, string][],
  extra: Partial<StageEvent> = {},
): StageEvent => ({
  stage: name,
  status: 'completed',
  detail: null,
  facts,
  duration_ms: 100,
  attempt: 1,
  ...extra,
});

/** A contested turn: a question asked, three dimensions assumed, four drafts. */
const CONTESTED: StageEvent[] = [
  stage('intent_classification', [['intent', 'analytical_sql']]),
  stage('domain_scoping', [], {
    status: 'skipped',
    detail: 'no business domain matched — the whole catalogue stays in scope',
  }),
  stage('schema_linking', [
    ['objects', '9'],
    ['columns', '21'],
    ['join paths', '3'],
  ]),
  stage(
    'ambiguity_gate',
    [
      ['confidence', 'entity 0.96 · metric 0.88'],
      ['assumed', 'time_range=all history · grain=one row per customer'],
      ['rule defaults', 'time_range via default_period'],
      ['contested', 'yes'],
    ],
    { detail: '2 dimensions assumed, none left to ask' },
  ),
  stage('ambiguity_interrupt', [
    ['dimension', 'metric'],
    ['your answer', 'Credit status classified as good'],
    ['rounds', '1'],
  ]),
  stage('planning', [['grounded in', 'local.tpcds.store_sales, local.tpcds.customer']]),
  stage('candidate_generation', [['candidates', '4']], { duration_ms: 6400 }),
  stage('static_validation', [['cleared', '3']]),
  stage('critique', [['scores', '#0 0.92 · #1 0.71 · #2 0.68']]),
  stage('ambiguity_probing', [
    ['probes', '2'],
    ['resolved to', '#0'],
  ]),
  stage('candidate_selection', [
    ['method', 'probe_resolved'],
    ['why', 'only candidate 0 predicted the real count'],
  ]),
  stage('rewrite_and_cost_gate', [['verdict', 'within budget']]),
  stage('guarded_execution', [['rows', '100']]),
];

describe('buildDecisions', () => {
  it('surfaces the answer, the assumptions and the contest', () => {
    expect(buildDecisions(CONTESTED).map((decision) => decision.key)).toEqual([
      'answered',
      'assumed',
      'chosen',
    ]);
  });

  it('names the rule behind an assumption the user never stated', () => {
    // `applied_defaults` records which rule fired precisely so someone can go
    // and change it. A value with no provenance is a value nobody can correct.
    const rows = buildDecisions(CONTESTED).find((d) => d.key === 'assumed')?.rows;

    expect(rows).toEqual([
      { label: 'time_range', value: 'all history · rule default_period' },
      { label: 'grain', value: 'one row per customer' },
    ]);
  });

  it('marks the candidate the probe agreed with', () => {
    const chosen = buildDecisions(CONTESTED).find((d) => d.key === 'chosen');

    expect(chosen?.lead).toBe('only candidate 0 predicted the real count');
    expect(chosen?.aside).toBe('4 → 1');
    expect(chosen?.rows[0]).toEqual({ label: '#0', value: '0.92 · probe agreed' });
    expect(chosen?.rows[1]).toEqual({ label: '#1', value: '0.71' });
    expect(chosen?.note).toBe('3 of 4 cleared validation.');
  });

  it('claims nothing was decided when nothing was', () => {
    // A turn nobody had to ask about has no answered question and no contest.
    // An empty card would assert a decision that never happened.
    const straightforward: StageEvent[] = [
      stage('schema_linking', [['objects', '2']]),
      stage('candidate_generation', [['candidates', '1']]),
      stage('candidate_selection', [
        ['method', 'single_survivor'],
        ['why', 'only one candidate survived validation'],
      ]),
      stage('guarded_execution', [['rows', '12']]),
    ];

    expect(buildDecisions(straightforward)).toEqual([]);
  });

  it('shows nothing for a trail recorded before facts existed', () => {
    const legacy: StageEvent[] = [
      { stage: 'planning', status: 'completed', detail: 'sum sales by month' },
    ];

    expect(buildDecisions(legacy)).toEqual([]);
    expect(buildRows(legacy, false)[0].facts).toEqual([]);
  });
});

describe('glanceOf', () => {
  it('puts the noun in front of the number so a bare count is readable', () => {
    const rows = buildRows(CONTESTED, false);
    const glance = (key: string) => glanceOf(rows.find((row) => row.key === key)!);

    expect(glance('schema_linking')).toBe('9 objects · 3 joins');
    expect(glance('candidate_generation')).toBe('4 candidates');
    expect(glance('critique')).toBe('top 0.92');
    expect(glance('guarded_execution')).toBe('100 rows');
    expect(glance('intent_classification')).toBe('analytical_sql');
  });

  it('says only that a skipped stage was skipped', () => {
    // A count beside it would describe work that never happened.
    const rows = buildRows(CONTESTED, false);

    expect(glanceOf(rows.find((row) => row.key === 'domain_scoping')!)).toBe('skipped');
  });

  it('falls back to a first fact for a stage it has never heard of', () => {
    const rows = buildRows([stage('semantic_reranking', [['reranked', '12']])], false);

    expect(glanceOf(rows[0])).toBe('12');
  });
});

describe('StageRail', () => {
  it('leads with the verdict rather than with the first stage', () => {
    // The row count appears twice on purpose — as the outcome up top, and as
    // the execution step down in the trail. Only the first is the verdict.
    render(<StageRail stages={CONTESTED} running={false} startedAt={null} />);
    const trail = screen.getByRole('region', { name: 'Full trail' });

    expect(screen.getByText('Validated, then run')).toBeInTheDocument();
    expect(within(trail).queryByText('Validated, then run')).not.toBeInTheDocument();
  });

  it('shows the answer the user gave above the trail', () => {
    render(<StageRail stages={CONTESTED} running={false} startedAt={null} />);
    const decisions = screen.getByRole('region', { name: 'What decided this answer' });

    expect(within(decisions).getByText('Credit status classified as good')).toBeVisible();
    expect(within(decisions).getByText('You answered')).toBeInTheDocument();
    expect(
      within(decisions).getByText('Wrong? Say so in a follow-up and the gate re-asks.'),
    ).toBeVisible();
  });

  it('groups the trail by what the pipeline was doing', () => {
    render(<StageRail stages={CONTESTED} running={false} startedAt={null} />);

    expect(screen.getByText('Read the question')).toBeInTheDocument();
    expect(screen.getByText('Settle the ambiguity')).toBeInTheDocument();
    expect(screen.getByText('Prove it')).toBeInTheDocument();
    expect(screen.getByText('Run it')).toBeInTheDocument();
  });

  it('counts the stages that ran, not the stages that reported', () => {
    render(<StageRail stages={CONTESTED} running={false} startedAt={null} />);

    // Thirteen events, one of them a stage the pipeline chose not to run.
    expect(screen.getByText(/12 of 13 stages ran/)).toBeInTheDocument();
  });

  it('does not print the sentence above the facts it was built from', () => {
    // `guarded_execution` reports detail "100 rows" and fact rows=100. Showing
    // both puts "100 rows" directly above "ROWS 100", which reads as a bug.
    render(<StageRail stages={CONTESTED} running={false} startedAt={null} />);
    const trail = screen.getByRole('region', { name: 'Full trail' });

    // The default-open row is the last that reported: execution.
    expect(within(trail).getByText('rows')).toBeVisible();
    expect(within(trail).queryByText('100 rows', { selector: 'p' })).not.toBeInTheDocument();
  });

  it('falls back to the sentence for a trail that has no facts', () => {
    // Rows recorded before the backend sent facts have only the sentence, and
    // dropping it would leave those stages with nothing to open at all.
    const legacy: StageEvent[] = [
      { stage: 'schema_linking', status: 'completed', detail: '7 objects linked' },
    ];

    render(<StageRail stages={legacy} running={false} startedAt={null} />);

    expect(screen.getByText('7 objects linked')).toBeVisible();
  });

  it('shows no elapsed total when nothing measured one', () => {
    const unmeasured: StageEvent[] = [
      { stage: 'planning', status: 'completed', detail: 'sum sales by month' },
    ];

    render(<StageRail stages={unmeasured} running={false} startedAt={null} />);

    expect(screen.getByText('1 of 1 stages ran')).toBeInTheDocument();
  });
});
