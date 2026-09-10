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
      <SelectTrigger className="h-7 w-[118px] border-[var(--line)] text-[0.72rem]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {DIALECTS.map((dialect) => (
          <SelectItem key={dialect} value={dialect} className="text-[0.72rem]">
            {dialect}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
