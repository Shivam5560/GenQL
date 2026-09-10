'use client';

import { useState } from 'react';
import { DialectField } from '@/components/datasources/dialect-field';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { Datasource, UpdateDatasourceArgs } from '@/lib/types';

/**
 * Edit where a datasource points, or turn it off.
 *
 * Submits a diff, not a form: `PATCH` treats an absent field as "leave alone",
 * so sending every field back would let a stale form overwrite a change
 * somebody else just made — and would overwrite the password with the blank
 * this form always starts with, since no endpoint ever hands that back.
 *
 * The host, port and database are read out of `endpoint` because that is the
 * only shape the API returns them in. The username is deliberately not
 * returned at all, so this form can set a new one but cannot show the current
 * one; leaving it blank leaves it as it was.
 */
function parseEndpoint(endpoint: string | null | undefined) {
  // Positional groups, not named ones: this project's TypeScript target
  // predates named capture groups and rejects them outright.
  const match = /^(.*?)(?::(\d+))?(?:\/(.*))?$/.exec(endpoint ?? '');
  return { host: match?.[1] ?? '', port: match?.[2] ?? '', database: match?.[3] ?? '' };
}

export function EditForm({
  datasource,
  dialects,
  onSubmit,
  onCancel,
  submitting,
  error,
}: {
  datasource: Datasource;
  dialects: string[];
  onSubmit: (args: UpdateDatasourceArgs) => void;
  onCancel: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const initial = parseEndpoint(datasource.endpoint);
  const [dialect, setDialect] = useState(datasource.dialect);
  const [host, setHost] = useState(initial.host);
  const [port, setPort] = useState(initial.port);
  const [database, setDatabase] = useState(initial.database);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [description, setDescription] = useState(datasource.description ?? '');
  const [enabled, setEnabled] = useState(datasource.enabled);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const args: UpdateDatasourceArgs = {};
    if (dialect !== datasource.dialect) args.dialect = dialect;
    if (host.trim() !== initial.host) args.host = host.trim();
    if (port !== initial.port) args.port = Number(port) || undefined;
    if (database.trim() !== initial.database) args.database = database.trim();
    if (username.trim()) args.username = username.trim();
    if (password) args.password = password;
    if (description !== (datasource.description ?? '')) args.description = description;
    if (enabled !== datasource.enabled) args.enabled = enabled;
    onSubmit(args);
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4 rounded-md border border-[var(--line)] bg-[var(--panel)] px-5 py-5"
    >
      <div>
        <h2 className="text-sm font-semibold">Edit {datasource.name}</h2>
        <p className="mt-1 max-w-[62ch] text-sm text-[var(--mute)]">
          Only what you change is sent. What was already surveyed stays surveyed — re-run the
          survey yourself if this edit points somewhere new.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <DialectField id="edit-dialect" dialects={dialects} value={dialect} onChange={setDialect} />
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-description">Description</Label>
          <Input
            id="edit-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-host">Host</Label>
          <Input
            id="edit-host"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-port">Port</Label>
          <Input
            id="edit-port"
            inputMode="numeric"
            value={port}
            onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ''))}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-database">Database</Label>
          <Input
            id="edit-database"
            value={database}
            onChange={(e) => setDatabase(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-username">User</Label>
          <Input
            id="edit-username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="unchanged"
            autoComplete="off"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-password">Password</Label>
        <Input
          id="edit-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="unchanged"
          autoComplete="new-password"
          aria-describedby="edit-password-help"
        />
        <p id="edit-password-help" className="text-[0.78rem] text-[var(--mute)]">
          Leave blank to keep the stored one.
        </p>
      </div>

      <label className="flex items-center gap-2 text-sm text-[var(--mute)]">
        <input
          id="edit-enabled"
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="size-3.5 accent-[var(--brand)]"
        />
        Enabled
      </label>

      {error && <p className="text-sm text-[var(--danger,#dc2626)]">{error}</p>}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : 'Save changes'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
