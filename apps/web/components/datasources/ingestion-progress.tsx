'use client';

import type { IngestionJob, IngestionStep } from '@/lib/types';

/**
 * A datasource becoming queryable, step by step.
 *
 * The six steps are the pipeline that used to be six CLI commands run in
 * order by hand. Naming them here is the point: when `semantic_compile` fails
 * after twelve minutes of profiling, "compile failed" plus a Resume button is
 * worth far more than a spinner that turns into an error.
 *
 * Steps come from the server, in the server's order, rather than from a list
 * held here — a stage added to the pipeline later appears without this file
 * changing.
 */

const LABELS: Record<string, string> = {
  schema_registration: 'Register schemas',
  discovery: 'Survey the warehouse',
  semantic_overlay: 'Apply overlay',
  semantic_compile: 'Compile search index',
  graph_analysis: 'Analyze graph',
  domain_discovery: 'Discover domains',
};

function label(step: IngestionStep): string {
  return LABELS[step.name] ?? step.name.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

function duration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

function StepRow({ step }: { step: IngestionStep }) {
  const tone =
    step.status === 'succeeded'
      ? 'bg-[var(--ok)]'
      : step.status === 'failed'
        ? 'bg-[var(--bad)]'
        : step.status === 'running'
          ? 'gq-pulse bg-[var(--brand)]'
          : step.status === 'skipped'
            ? 'bg-[var(--mute)] opacity-50'
            : 'bg-[var(--line)]';

  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <span aria-hidden className={`mt-[0.42rem] size-[6px] shrink-0 rounded-full ${tone}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span
            className={`text-sm ${
              step.status === 'pending' ? 'text-[var(--mute)] opacity-60' : 'text-[var(--ink)]'
            }`}
          >
            {label(step)}
          </span>
          {step.duration_ms > 0 && (
            <span className="shrink-0 font-mono text-[0.68rem] text-[var(--mute)]">
              {duration(step.duration_ms)}
            </span>
          )}
        </div>
        {step.detail && (
          <p
            className={`mt-0.5 break-words font-mono text-[0.7rem] leading-snug ${
              step.status === 'failed' ? 'text-[var(--bad)]' : 'text-[var(--mute)]'
            }`}
          >
            {step.detail}
          </p>
        )}
      </div>
    </li>
  );
}

export function IngestionProgress({
  job,
  onRetry,
}: {
  job: IngestionJob;
  /** Resume from the step that failed, rather than re-profiling everything. */
  onRetry?: (startFrom?: string) => void;
}) {
  const done = job.steps.filter((s) => s.status === 'succeeded' || s.status === 'skipped').length;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-[var(--line)] bg-[var(--panel-2)] px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
          {job.status === 'queued'
            ? 'Queued'
            : job.status === 'running'
              ? `Preparing — ${done} of ${job.steps.length}`
              : job.status === 'succeeded'
                ? 'Ready to query'
                : 'Could not be prepared'}
        </span>
        {job.status === 'failed' && onRetry && (
          <div className="flex gap-2">
            {job.error_step && (
              <button
                type="button"
                onClick={() => onRetry(job.error_step ?? undefined)}
                className="font-eyebrow rounded border border-[var(--line)] px-2 py-1 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]"
              >
                Resume here
              </button>
            )}
            <button
              type="button"
              onClick={() => onRetry(undefined)}
              className="font-eyebrow rounded border border-[var(--line)] px-2 py-1 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]"
            >
              Start over
            </button>
          </div>
        )}
      </div>
      <ol className="flex flex-col divide-y divide-[var(--line)]">
        {job.steps.map((step) => (
          <StepRow key={step.name} step={step} />
        ))}
      </ol>
      {job.status === 'failed' && job.error && (
        <p role="alert" className="mt-1 break-words text-sm text-[var(--bad)]">
          {job.error}
        </p>
      )}
    </div>
  );
}
