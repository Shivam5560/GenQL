'use client';

import { Label } from '@/components/ui/label';

/**
 * The dialect picker, shared by the connect and edit forms.
 *
 * A native `<select>` rather than the app's Select primitive: that one renders
 * its list in a portal, which buys keyboard niceties this field does not need
 * and costs a form control that browsers already validate and submit. The
 * options come from `GET /v1/datasources/dialects` — the catalog-reader
 * registry's own answer — so a warehouse type nobody implemented can never be
 * offered, and implementing one is enough to make it appear here.
 */
export function DialectField({
  id = 'ds-dialect',
  dialects,
  value,
  onChange,
}: {
  id?: string;
  dialects: string[];
  value: string;
  onChange: (dialect: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>Dialect</Label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-lg border border-[var(--line)] bg-[var(--panel-2)] px-2.5 text-sm outline-none focus-visible:border-[var(--brand)]"
      >
        {dialects.map((dialect) => (
          <option key={dialect} value={dialect}>
            {dialect}
          </option>
        ))}
      </select>
    </div>
  );
}
