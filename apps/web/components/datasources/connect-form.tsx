'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { RegisterDatasourceArgs } from '@/lib/types';

/**
 * Connect a warehouse.
 *
 * This form used to ask for the NAME of an environment variable already set on
 * the server — which meant nobody could connect their own warehouse without
 * shell access to the box AuraSQL runs on. It now asks for the five things a
 * person actually has: host, port, database, user, password. The password is
 * encrypted before it is stored and is never sent back by any endpoint, so
 * this field is write-only in the literal sense — reopening the form on an
 * existing datasource would show it blank.
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
  const [dialect] = useState('postgres');
  const [host, setHost] = useState('');
  const [port, setPort] = useState('5432');
  const [database, setDatabase] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [ssl, setSsl] = useState(false);
  const [schemas, setSchemas] = useState('');
  const [description, setDescription] = useState('');

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      name: name.trim(),
      dialect,
      host: host.trim(),
      // Coerced here rather than held as a number in state: an <input> that
      // round-trips through Number() cannot be cleared, and a half-typed port
      // should not become NaN mid-keystroke.
      port: Number(port) || 5432,
      database: database.trim(),
      username: username.trim(),
      password,
      options: ssl ? 'sslmode=require' : null,
      description: description.trim() || null,
      schemas: schemas
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    });
  }

  const ready = name.trim() && host.trim() && database.trim() && username.trim();

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4 rounded-md border border-[var(--line)] bg-[var(--panel)] px-5 py-5"
    >
      <div>
        <h2 className="text-sm font-semibold">Connect a warehouse</h2>
        <p className="mt-1 max-w-[62ch] text-sm text-[var(--mute)]">
          AuraSQL will survey the schemas you name, profile them, build a search index, and map
          the join graph. That takes minutes, so feel free to leave this page. We will tell you
          when it is ready.
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
            aria-describedby="ds-name-help"
          />
          <p id="ds-name-help" className="text-[0.78rem] text-[var(--mute)]">
            What you will call it here. Not the database name.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-dialect">Dialect</Label>
          <Input id="ds-dialect" value="PostgreSQL" readOnly disabled />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-host">Host</Label>
          <Input
            id="ds-host"
            required
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="warehouse.internal"
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-port">Port</Label>
          <Input
            id="ds-port"
            required
            inputMode="numeric"
            value={port}
            onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ''))}
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ds-database">Database</Label>
        <Input
          id="ds-database"
          required
          value={database}
          onChange={(e) => setDatabase(e.target.value)}
          placeholder="analytics"
          autoComplete="off"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-username">User</Label>
          <Input
            id="ds-username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="aurasql_reader"
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ds-password">Password</Label>
          <Input
            id="ds-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            aria-describedby="ds-password-help"
          />
          <p id="ds-password-help" className="text-[0.78rem] text-[var(--mute)]">
            Encrypted before it is stored, and never sent back.
          </p>
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-[var(--mute)]">
        <input
          type="checkbox"
          checked={ssl}
          onChange={(e) => setSsl(e.target.checked)}
          className="size-3.5 accent-[var(--brand)]"
        />
        Require SSL
      </label>

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
          {submitting ? 'Connecting…' : 'Connect and survey'}
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
