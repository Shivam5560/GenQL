'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { RegisterDatasourceArgs } from '@/lib/types';

/**
 * Connect a warehouse.
 *
 * The DSN field asks for the NAME of an environment variable, not a
 * connection string — GenQL deliberately never stores warehouse credentials,
 * and reads the DSN from the server's own environment at connect time. The
 * form says so plainly rather than letting someone paste a password into a
 * field that will refuse it.
 */
export function ConnectForm({
  onSubmit,
  onCancel,
  submitting,
  error,
}: {
  onSubmit: (args: RegisterDatasourceArgs) => void;
  onCancel: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const [name, setName] = useState('');
  const [dialect, setDialect] = useState('postgres');
  const [dsnEnvVar, setDsnEnvVar] = useState('');
  const [schemas, setSchemas] = useState('');
  const [description, setDescription] = useState('');

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      name: name.trim(),
      dialect: dialect.trim(),
      dsn_env_var: dsnEnvVar.trim(),
      description: description.trim() || null,
      schemas: schemas
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    });
  }

  const ready = name.trim() && dsnEnvVar.trim();

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4 rounded-md border border-[var(--line)] bg-[var(--panel)] px-5 py-5"
    >
      <div>
        <h2 className="text-sm font-semibold">Connect a warehouse</h2>
        <p className="mt-1 max-w-[62ch] text-sm text-[var(--mute)]">
          GenQL will survey the schemas you name, profile them, build a search index, and map
          the join graph. That takes minutes — you can leave this page and we will tell you when
          it is ready.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-name">Name</Label>
          <Input
            id="ds-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="warehouse"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-dialect">Dialect</Label>
          <Input
            id="ds-dialect"
            required
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-dsn">Environment variable holding the DSN</Label>
        <Input
          id="ds-dsn"
          required
          value={dsnEnvVar}
          onChange={(e) => setDsnEnvVar(e.target.value)}
          placeholder="WAREHOUSE_DSN"
          aria-describedby="ds-dsn-help"
        />
        <p id="ds-dsn-help" className="text-[0.78rem] leading-relaxed text-[var(--mute)]">
          The variable&apos;s name, not the connection string. GenQL never stores warehouse
          credentials — it reads this variable from the server&apos;s environment when it
          connects.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-schemas">Schemas</Label>
        <Input
          id="ds-schemas"
          value={schemas}
          onChange={(e) => setSchemas(e.target.value)}
          placeholder="public, sales, billing"
          aria-describedby="ds-schemas-help"
        />
        <p id="ds-schemas-help" className="text-[0.78rem] text-[var(--mute)]">
          Comma separated. Only these are surveyed and only these can be queried.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-description">Description</Label>
        <Input
          id="ds-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Production orders and billing"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--bad)]">
          {error}
        </p>
      )}

      <div className="flex items-center gap-2.5">
        <Button type="submit" disabled={submitting || !ready}>
          {submitting ? 'Starting…' : 'Connect and survey'}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="font-eyebrow rounded border border-[var(--line)] px-2.5 py-1.5 text-[0.68rem] uppercase tracking-wide text-[var(--mute)]"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
