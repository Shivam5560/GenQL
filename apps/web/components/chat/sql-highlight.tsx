import { tokenizeSql, type SqlTokenKind } from '@/lib/sql-format';

/**
 * Colour by role, not by rainbow.
 *
 * Three roles get a colour: structure (keywords), values (strings and
 * numbers) and everything that names something (identifiers, which keep the
 * body colour because they are what the reader is actually checking). The
 * comparison a person makes against this block is "did it filter the right
 * column on the right value" — so the columns and the values are what have to
 * be findable, and punctuation should recede.
 */
const CLASSES: Record<SqlTokenKind, string> = {
  keyword: 'text-[var(--code-key)] font-semibold',
  function: 'text-[var(--ink)] font-semibold',
  string: 'text-[var(--code-lit)]',
  number: 'text-[var(--code-lit)]',
  comment: 'text-[var(--mute)] italic',
  operator: 'text-[var(--mute)]',
  punctuation: 'text-[var(--mute)]',
  identifier: 'text-[var(--ink)]',
  whitespace: '',
};

export function SqlHighlight({ sql }: { sql: string }) {
  const tokens = tokenizeSql(sql);

  return (
    // Ligatures off. JetBrains Mono draws `<=` as a single `≤` glyph and `!=`
    // as `≠` — characters that are not in the statement and are not valid in
    // most dialects. On a block whose whole job is to be checked against what
    // will run, a font that silently substitutes operators is a bug.
    <code className="font-mono [font-feature-settings:'calt'_0] [font-variant-ligatures:none]">
      {tokens.map((token, index) =>
        token.kind === 'whitespace' ? (
          token.text
        ) : (
          <span key={index} className={CLASSES[token.kind]}>
            {token.text}
          </span>
        ),
      )}
    </code>
  );
}
