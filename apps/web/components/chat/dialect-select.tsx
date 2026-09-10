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
      <SelectTrigger className="h-7 w-[118px] border-[var(--line)] font-eyebrow text-[0.62rem] uppercase tracking-[0.08em]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {DIALECTS.map((dialect) => (
          <SelectItem
            key={dialect}
            value={dialect}
            className="font-eyebrow text-[0.62rem] uppercase tracking-[0.08em]"
          >
            {dialect}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
