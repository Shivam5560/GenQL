'use client';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const DIALECTS = ['Postgres', 'Snowflake', 'BigQuery', 'MySQL', 'DuckDB'];

export function DialectSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (dialect: string) => void;
}) {
  return (
    <Select value={value} onValueChange={(next) => next && onChange(next)}>
      <SelectTrigger className="font-eyebrow h-7 w-[124px] border-[var(--line)] text-[0.68rem] uppercase">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {DIALECTS.map((dialect) => (
          <SelectItem key={dialect} value={dialect} className="font-eyebrow text-[0.68rem] uppercase">
            {dialect}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
