'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import {
  ApiError,
  getOnboarding,
  listDatasources,
  listDialects,
  registerDatasource,
  removeDatasource,
  retryOnboarding,
  streamOnboarding,
  updateDatasource,
} from '@/lib/api-client';
import { ConnectForm } from '@/components/datasources/connect-form';
import { DatasourceRow } from '@/components/datasources/datasource-row';
import { EditForm } from '@/components/datasources/edit-form';
import { IngestionProgress } from '@/components/datasources/ingestion-progress';
import { Button } from '@/components/ui/button';
import type {
  Datasource,
  IngestionJob,
  RegisterDatasourceArgs,
  UpdateDatasourceArgs,
} from '@/lib/types';

const GENERIC_ERROR = 'Something went wrong. Try again.';

function DatasourceRowSkeleton() {
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="h-4 w-32 animate-pulse rounded bg-[var(--panel-2)]" />
        <div className="h-3 w-14 animate-pulse rounded bg-[var(--panel-2)]" />
      </div>
      <div className="mt-2 h-3 w-2/3 animate-pulse rounded bg-[var(--panel-2)]" />
    </div>
  );
}

/** Turns an ApiError into the sentence a person can act on. */
function describe(reason: unknown): string {
  if (!(reason instanceof ApiError)) return GENERIC_ERROR;
  const body = reason.body as { detail?: string } | null;
  return body?.detail ?? GENERIC_ERROR;
}

export default function DatasourcesPage() {
  const { session } = useAuth();
  const [datasources, setDatasources] = useState<Datasource[] | null>(null);
  const [jobs, setJobs] = useState<Record<string, IngestionJob>>({});
  const [connecting, setConnecting] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  // Registered dialects, asked for once. Falls back to the one dialect that
  // has always been implemented if the request fails, so a dropped connection
  // leaves the form usable rather than empty.
  const [dialects, setDialects] = useState<string[]>(['postgres']);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // One live stream per datasource being ingested, torn down on unmount.
  const streamsRef = useRef(new Map<string, AbortController>());

  const accessToken = session?.accessToken;

  /**
   * Follow one datasource's ingestion.
   *
   * Idempotent by name: opening the page while three warehouses are being
   * surveyed subscribes to each exactly once, and a re-render does not stack
   * a second connection on top of a live one.
   */
  const watch = useCallback(
    (name: string) => {
      if (!accessToken || streamsRef.current.has(name)) return;
      const controller = new AbortController();
      streamsRef.current.set(name, controller);
      void streamOnboarding(
        accessToken,
        name,
        {
          onStep: (step) => {
            setJobs((prev) => {
              const job = prev[name];
              if (!job) return prev;
              const steps = job.steps.some((s) => s.name === step.name)
                ? job.steps.map((s) => (s.name === step.name ? { ...s, ...step } : s))
                : [...job.steps, step];
              return { ...prev, [name]: { ...job, status: 'running', steps } };
            });
          },
          onProgress: ({ progress }) => {
            setJobs((prev) => {
              const job = prev[name];
              return job ? { ...prev, [name]: { ...job, progress } } : prev;
            });
          },
          onDone: (job) => {
            setJobs((prev) => ({ ...prev, [name]: job }));
            streamsRef.current.delete(name);
          },
          onError: (error) => {
            setJobs((prev) => {
              const job = prev[name];
              return job
                ? {
                    ...prev,
                    [name]: {
                      ...job,
                      status: 'failed',
                      error: error.detail,
                      error_step: error.step,
                    },
                  }
                : prev;
            });
            streamsRef.current.delete(name);
          },
        },
        controller.signal,
      );
    },
    [accessToken],
  );

  const load = useCallback(() => {
    if (!accessToken) return;
    listDatasources(accessToken)
      .then((list) => {
        setDatasources(list);
        // Ask each datasource for its ingestion state. A 404 means it was
        // registered by the CLI and never had a job — normal, not an error.
        list.forEach((ds) => {
          getOnboarding(accessToken, ds.name)
            .then((job) => {
              setJobs((prev) => ({ ...prev, [ds.name]: job }));
              if (job.status === 'queued' || job.status === 'running') watch(ds.name);
            })
            .catch(() => {});
        });
      })
      .catch(() => toast.error(GENERIC_ERROR));
  }, [accessToken, watch]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!accessToken) return;
    listDialects(accessToken)
      .then((registered) => {
        if (registered.length) setDialects(registered);
      })
      .catch(() => {});
  }, [accessToken]);

  useEffect(() => {
    const streams = streamsRef.current;
    return () => {
      streams.forEach((controller) => controller.abort());
      streams.clear();
    };
  }, []);

  function onConnect(args: RegisterDatasourceArgs) {
    if (!accessToken) return;
    setSubmitting(true);
    setFormError(null);
    registerDatasource(accessToken, args)
      .then(({ datasource, job }) => {
        setDatasources((prev) => [...(prev ?? []), datasource]);
        setJobs((prev) => ({ ...prev, [datasource.name]: job }));
        setConnecting(false);
        watch(datasource.name);
        toast.success(`${datasource.name} queued. Surveying now.`);
      })
      .catch((reason: unknown) => setFormError(describe(reason)))
      .finally(() => setSubmitting(false));
  }

  function onSave(name: string, args: UpdateDatasourceArgs) {
    if (!accessToken) return;
    // An empty edit is a no-op the server would happily accept; closing the
    // form is the honest response to "save" with nothing changed.
    if (Object.keys(args).length === 0) {
      setEditing(null);
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateDatasource(accessToken, name, args)
      .then((edited) => {
        setDatasources((prev) =>
          (prev ?? []).map((ds) => (ds.name === edited.name ? edited : ds)),
        );
        setEditing(null);
        toast.success(`${edited.name} updated.`);
      })
      .catch((reason: unknown) => setFormError(describe(reason)))
      .finally(() => setSubmitting(false));
  }

  function onRemove(name: string) {
    if (!accessToken) return;
    removeDatasource(accessToken, name)
      .then(() => {
        streamsRef.current.get(name)?.abort();
        streamsRef.current.delete(name);
        setDatasources((prev) => (prev ?? []).filter((ds) => ds.name !== name));
        setJobs((prev) => {
          const rest = { ...prev };
          delete rest[name];
          return rest;
        });
        toast.success(`${name} removed.`);
      })
      .catch((reason: unknown) => toast.error(describe(reason)));
  }

  function onRetry(name: string, startFrom?: string) {
    if (!accessToken) return;
    retryOnboarding(accessToken, name, startFrom)
      .then((job) => {
        setJobs((prev) => ({ ...prev, [name]: job }));
        watch(name);
      })
      .catch((reason: unknown) => toast.error(describe(reason)));
  }

  return (
    <main className="mx-auto w-full max-w-[900px] overflow-y-auto px-7 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="font-eyebrow text-xs uppercase tracking-wide text-[var(--mute)]">
          Datasources
        </h1>
        {!connecting && (
          <Button type="button" onClick={() => setConnecting(true)}>
            Connect a warehouse
          </Button>
        )}
      </div>

      {connecting && (
        <div className="mb-5">
          <ConnectForm
            dialects={dialects}
            onSubmit={onConnect}
            onCancel={() => {
              setConnecting(false);
              setFormError(null);
            }}
            submitting={submitting}
            error={formError}
          />
        </div>
      )}

      {datasources === null ? (
        <div className="flex flex-col gap-2.5">
          <DatasourceRowSkeleton />
          <DatasourceRowSkeleton />
          <DatasourceRowSkeleton />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {datasources.map((ds) => {
            const job = jobs[ds.name];
            const preparing = job && job.status !== 'succeeded';
            return (
              <div key={ds.name} className="flex flex-col gap-2.5">
                {preparing && (
                  <span className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--brand)]">
                    {job.status === 'failed' ? 'Not ready' : 'Preparing'}
                  </span>
                )}
                {editing === ds.name ? (
                  <EditForm
                    datasource={ds}
                    dialects={dialects}
                    onSubmit={(args) => onSave(ds.name, args)}
                    onCancel={() => {
                      setEditing(null);
                      setFormError(null);
                    }}
                    submitting={submitting}
                    error={formError}
                  />
                ) : (
                  <DatasourceRow
                    datasource={ds}
                    onEdit={() => {
                      setEditing(ds.name);
                      setFormError(null);
                    }}
                    onRemove={() => onRemove(ds.name)}
                  />
                )}
                {preparing && (
                  <IngestionProgress
                    job={job}
                    onRetry={(startFrom) => onRetry(ds.name, startFrom)}
                  />
                )}
              </div>
            );
          })}
          {datasources.length === 0 && !connecting && (
            <p className="text-sm text-[var(--mute)]">
              No warehouses connected yet. Connect one to start asking questions.
            </p>
          )}
        </div>
      )}
    </main>
  );
}
