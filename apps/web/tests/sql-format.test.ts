import { describe, expect, it } from 'vitest';
import { formatSql, tokenizeSql } from '@/lib/sql-format';

/** The token stream, whitespace removed — what must survive formatting. */
const meaning = (sql: string) =>
  tokenizeSql(sql)
    .filter((token) => token.kind !== 'whitespace')
    .map((token) => token.text)
    .join(' ');

const STATEMENTS = [
  "select state, count(distinct store_id) as n from analytics.store_locations where opened_at <= DATE '2024-12-31' and status = 'active' group by state order by n desc limit 10;",
  "with recent as (select id, region from sales.orders where created_at > now() - interval '30 days') select r.region, count(*) from recent r left outer join dim.region d on d.id = r.region group by r.region",
  "select a from t where name = 'it''s -- not a comment' and x in (1, 2, 3)",
  'select region, sum(amount) filter (where paid) from (select * from sales.orders) o group by region having sum(amount) > 1000',
  "select \"select\", count(*) from \"from\" where \"where\" = 1e-3",
];

describe('tokenizeSql', () => {
  it('accounts for every character, so nothing can be silently dropped', () => {
    for (const sql of STATEMENTS) {
      expect(
        tokenizeSql(sql)
          .map((token) => token.text)
          .join(''),
      ).toBe(sql);
    }
  });

  it('does not mistake SQL inside a string literal for SQL', () => {
    // The whole reason formatting is safe to apply to a validated statement:
    // a `--` in a value is a value, not the start of a comment.
    const tokens = tokenizeSql("select 'a -- b' as x");
    expect(tokens.find((t) => t.kind === 'comment')).toBeUndefined();
    expect(tokens.filter((t) => t.kind === 'string').map((t) => t.text)).toEqual(["'a -- b'"]);
  });

  it('reads a quoted identifier as a name even when it spells a keyword', () => {
    const tokens = tokenizeSql('select "from" from t').filter((t) => t.kind !== 'whitespace');
    expect(tokens[1]).toEqual({ kind: 'identifier', text: '"from"' });
    expect(tokens[2]).toEqual({ kind: 'keyword', text: 'from' });
  });

  it('separates a call from a keyword that happens to precede a paren', () => {
    const kinds = new Map(
      tokenizeSql('select count(*) from t where x in (1)')
        .filter((t) => t.kind !== 'whitespace')
        .map((t) => [t.text.toLowerCase(), t.kind]),
    );
    expect(kinds.get('count')).toBe('function');
    expect(kinds.get('in')).toBe('keyword');
  });
});

describe('formatSql', () => {
  it('changes only whitespace', () => {
    // This is the guarantee that makes it safe to show formatted SQL as the
    // SQL that ran. If this test fails, the display is lying.
    for (const sql of STATEMENTS) {
      expect(meaning(formatSql(sql))).toBe(meaning(sql));
    }
  });

  it('is stable — formatting formatted SQL is a no-op', () => {
    for (const sql of STATEMENTS) {
      const once = formatSql(sql);
      expect(formatSql(once)).toBe(once);
    }
  });

  it('puts each clause and each selected column on its own line', () => {
    const out = formatSql('select a, b from t where x = 1 and y = 2');
    expect(out.split('\n')).toEqual([
      'select',
      '  a,',
      '  b',
      'from t',
      'where x = 1',
      '  and y = 2',
    ]);
  });

  it('keeps a multi-word join on one line', () => {
    const out = formatSql('select a from t left outer join u on u.id = t.id');
    expect(out).toContain('left outer join u');
  });

  it('indents a subquery without breaking an argument list', () => {
    const out = formatSql('select coalesce(a, b) from (select a, b from t) s');
    expect(out).toContain('coalesce(a, b)');
    expect(out).toContain('from (\n  select');
  });

  it('returns empty input untouched rather than inventing a statement', () => {
    expect(formatSql('   ')).toBe('');
  });
});
