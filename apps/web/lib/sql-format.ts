/**
 * A SQL tokenizer, and a formatter built on top of it.
 *
 * Both exist for the same reason: the pipeline emits validated SQL as a single
 * run-on line, and a wall of undifferentiated monospace is not something a
 * person can check. Checking it is the entire point of showing it.
 *
 * The formatter only ever moves whitespace. It re-prints the token stream with
 * different spacing and never reorders, inserts, drops or re-cases a token, so
 * the SQL that comes out means exactly what the SQL that went in meant. That
 * guarantee is why this is safe to apply to statements the server has already
 * validated and is about to run — and it is only sound because the tokenizer
 * knows where strings and comments end, so a `--` or a keyword inside a
 * literal is never mistaken for one in the statement.
 */

export type SqlTokenKind =
  | 'keyword'
  | 'function'
  | 'string'
  | 'number'
  | 'comment'
  | 'operator'
  | 'punctuation'
  | 'identifier'
  | 'whitespace';

export interface SqlToken {
  kind: SqlTokenKind;
  text: string;
}

/**
 * Reserved words, upper-cased. Deliberately broad — a word wrongly listed here
 * only changes its colour, never its meaning, because nothing downstream
 * rewrites keywords.
 */
const KEYWORDS = new Set(
  (
    'select from where group by order having limit offset union intersect except all distinct as ' +
    'on using join inner left right full cross natural lateral and or not in exists between like ' +
    'ilike similar is null true false case when then else end with recursive over partition ' +
    'window rows range preceding following unbounded current row asc desc nulls first last ' +
    'insert into values update set delete returning cast filter within qualify fetch next only ' +
    'interval date time timestamp array any some cross'
  )
    .toUpperCase()
    .split(' '),
);

/**
 * Keywords that can be followed by `(` without being a function call, so that
 * `IN (…)` and `VALUES (…)` keep their keyword colour while `COUNT(`, `LEFT(`
 * and `CAST(` are recognised as calls.
 */
const NEVER_FUNCTIONS = new Set([
  'IN',
  'EXISTS',
  'VALUES',
  'AND',
  'OR',
  'NOT',
  'ON',
  'USING',
  'SELECT',
  'FROM',
  'WHERE',
  'WHEN',
  'THEN',
  'ELSE',
  'BETWEEN',
  'BY',
  'ALL',
  'ANY',
  'SOME',
  'AS',
  'OVER',
  'PARTITION',
  'RETURNING',
  'DISTINCT',
  'FILTER',
  'WITHIN',
]);

const PUNCTUATION = new Set(['(', ')', ',', ';', '.']);
const OPERATOR_CHARS = new Set(['+', '-', '*', '/', '%', '<', '>', '=', '!', '|', '&', '^', '~', ':', '@', '$', '#', '?', '[', ']', '{', '}']);

function isWordStart(ch: string): boolean {
  return /[A-Za-z_]/.test(ch);
}

function isWordChar(ch: string): boolean {
  return /[A-Za-z0-9_$]/.test(ch);
}

/** The next non-whitespace, non-comment character after `from`, or ''. */
function peekSignificant(sql: string, from: number): string {
  let i = from;
  while (i < sql.length) {
    const ch = sql[i];
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }
    if (ch === '-' && sql[i + 1] === '-') {
      while (i < sql.length && sql[i] !== '\n') i += 1;
      continue;
    }
    if (ch === '/' && sql[i + 1] === '*') {
      i += 2;
      while (i < sql.length && !(sql[i] === '*' && sql[i + 1] === '/')) i += 1;
      i += 2;
      continue;
    }
    return ch;
  }
  return '';
}

/**
 * Split SQL into typed tokens. Every character of the input lands in exactly
 * one token, so `tokens.map(t => t.text).join('')` reproduces the input.
 */
export function tokenizeSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  let i = 0;

  while (i < sql.length) {
    const ch = sql[i];
    const start = i;

    if (/\s/.test(ch)) {
      while (i < sql.length && /\s/.test(sql[i])) i += 1;
      tokens.push({ kind: 'whitespace', text: sql.slice(start, i) });
      continue;
    }

    // `-- …` runs to end of line; `/* … */` may span lines and is not nested.
    if (ch === '-' && sql[i + 1] === '-') {
      while (i < sql.length && sql[i] !== '\n') i += 1;
      tokens.push({ kind: 'comment', text: sql.slice(start, i) });
      continue;
    }
    if (ch === '/' && sql[i + 1] === '*') {
      i += 2;
      while (i < sql.length && !(sql[i] === '*' && sql[i + 1] === '/')) i += 1;
      i = Math.min(i + 2, sql.length);
      tokens.push({ kind: 'comment', text: sql.slice(start, i) });
      continue;
    }

    // Quoted runs. A doubled quote is an escaped quote in all three flavours;
    // backslash is deliberately NOT treated as an escape, because Postgres
    // with standard_conforming_strings (the default, and what the pipeline
    // targets) reads it as a literal backslash.
    if (ch === "'" || ch === '"' || ch === '`') {
      i += 1;
      while (i < sql.length) {
        if (sql[i] === ch) {
          if (sql[i + 1] === ch) {
            i += 2;
            continue;
          }
          i += 1;
          break;
        }
        i += 1;
      }
      // Only single quotes are values; the other two quote identifiers.
      tokens.push({ kind: ch === "'" ? 'string' : 'identifier', text: sql.slice(start, i) });
      continue;
    }

    if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(sql[i + 1] ?? ''))) {
      i += 1;
      while (i < sql.length && /[0-9.]/.test(sql[i])) i += 1;
      // Exponent, with an optional sign that must not be split off as an
      // operator: `1e-3` is one number.
      if (/[eE]/.test(sql[i] ?? '') && /[0-9+-]/.test(sql[i + 1] ?? '')) {
        i += 2;
        while (i < sql.length && /[0-9]/.test(sql[i])) i += 1;
      }
      tokens.push({ kind: 'number', text: sql.slice(start, i) });
      continue;
    }

    if (isWordStart(ch)) {
      while (i < sql.length && isWordChar(sql[i])) i += 1;
      const text = sql.slice(start, i);
      const upper = text.toUpperCase();
      const called = peekSignificant(sql, i) === '(' && !NEVER_FUNCTIONS.has(upper);
      tokens.push({
        kind: called ? 'function' : KEYWORDS.has(upper) ? 'keyword' : 'identifier',
        text,
      });
      continue;
    }

    if (PUNCTUATION.has(ch)) {
      i += 1;
      tokens.push({ kind: 'punctuation', text: ch });
      continue;
    }

    if (OPERATOR_CHARS.has(ch)) {
      while (i < sql.length && OPERATOR_CHARS.has(sql[i])) i += 1;
      tokens.push({ kind: 'operator', text: sql.slice(start, i) });
      continue;
    }

    // Anything unrecognised is still emitted, one character at a time, so the
    // round-trip guarantee holds for input this tokenizer has not met before.
    i += 1;
    tokens.push({ kind: 'operator', text: ch });
  }

  return tokens;
}

/** Clauses that open a new line at the current statement's own indent. */
const CLAUSE = new Set([
  'SELECT',
  'FROM',
  'WHERE',
  'HAVING',
  'LIMIT',
  'OFFSET',
  'UNION',
  'INTERSECT',
  'EXCEPT',
  'VALUES',
  'RETURNING',
  'WINDOW',
  'QUALIFY',
  'FETCH',
  'INSERT',
  'UPDATE',
  'DELETE',
  'WITH',
]);

/** Words that open a join, and so also open a line. */
const JOIN = new Set(['JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'NATURAL']);

/** Words that a `JOIN` may follow without starting a second line. */
const JOIN_PREFIX = new Set([...JOIN, 'OUTER']);

const INDENT = '  ';

interface Frame {
  /** Indent level that clauses of this statement sit at. */
  base: number;
  /** True for the top level and for any `(` that opens a subquery. */
  subquery: boolean;
}

/**
 * Re-print SQL with one clause per line and nested subqueries indented.
 *
 * Anything that cannot be re-printed confidently is returned untouched: this
 * is a readability aid, and a garbled statement is worse than a long one.
 */
export function formatSql(sql: string): string {
  const source = sql.trim();
  if (!source) return '';

  try {
    const tokens = tokenizeSql(source).filter((token) => token.kind !== 'whitespace');
    if (tokens.length === 0) return source;

    const stack: Frame[] = [{ base: 0, subquery: true }];
    const lines: string[] = [];
    let line = '';
    let previous: SqlToken | null = null;

    const frame = () => stack[stack.length - 1];
    const flush = () => {
      if (line.trim()) lines.push(line.trimEnd());
      line = '';
    };
    const open = (level: number) => {
      flush();
      line = INDENT.repeat(Math.max(level, 0));
    };
    const append = (text: string, spaced: boolean) => {
      line += line.trim() && spaced ? ` ${text}` : text;
    };

    for (let index = 0; index < tokens.length; index += 1) {
      const token = tokens[index];
      const upper = token.text.toUpperCase();
      const next = tokens[index + 1];
      const nextUpper = next?.text.toUpperCase() ?? '';
      const tightAfter = previous !== null && (previous.text === '(' || previous.text === '.');

      // A line comment eats the rest of its line, so it must own one.
      if (token.kind === 'comment') {
        if (token.text.startsWith('--')) {
          open(frame().base);
          append(token.text, false);
          flush();
        } else {
          append(token.text, true);
        }
        previous = token;
        continue;
      }

      if (token.kind === 'punctuation') {
        if (token.text === '(') {
          // A parenthesis followed by SELECT (or a CTE's WITH body) is a
          // statement of its own and gets its own indented block; every other
          // parenthesis — argument lists, grouping, IN lists — stays inline,
          // where it reads as the single expression it is.
          const isSubquery = nextUpper === 'SELECT' || nextUpper === 'WITH';
          append('(', previous !== null && !tightAfter && previous.kind !== 'function');
          stack.push({ base: frame().base + 1, subquery: isSubquery });
          if (isSubquery) open(frame().base);
          previous = token;
          continue;
        }
        if (token.text === ')') {
          const closing = stack.length > 1 ? stack.pop()! : frame();
          if (closing.subquery && stack.length >= 1) open(closing.base - 1);
          append(')', false);
          previous = token;
          continue;
        }
        if (token.text === ',') {
          append(',', false);
          // Only the statement's own lists break across lines. A comma inside
          // `count(a, b)` or an `IN (…)` list stays where it is.
          if (frame().subquery) open(frame().base + 1);
          previous = token;
          continue;
        }
        // `.` and `;` bind tight to what precedes them.
        append(token.text, false);
        if (token.text === ';') flush();
        previous = token;
        continue;
      }

      if (token.kind === 'keyword' && frame().subquery) {
        // `LEFT OUTER JOIN` is one clause opener, not three: only its first
        // word breaks the line, which is why this looks backwards at what was
        // already emitted rather than only forwards.
        const continuesJoin =
          previous !== null && JOIN_PREFIX.has(previous.text.toUpperCase());
        const startsClause =
          !continuesJoin &&
          (CLAUSE.has(upper) ||
            ((upper === 'GROUP' || upper === 'ORDER') && nextUpper === 'BY') ||
            (JOIN.has(upper) && (upper === 'JOIN' || nextUpper === 'JOIN' || nextUpper === 'OUTER')));

        if (startsClause) {
          open(frame().base);
          append(token.text, false);
          previous = token;
          // The select list is the one list that always breaks: it is the
          // part a reader checks column by column, and it is the part that
          // grows. `DISTINCT` and `ALL` belong to the SELECT, not the list,
          // so they stay on its line.
          if (upper === 'SELECT') {
            while (
              tokens[index + 1] &&
              ['DISTINCT', 'ALL'].includes(tokens[index + 1].text.toUpperCase())
            ) {
              index += 1;
              previous = tokens[index];
              append(previous.text, true);
            }
            open(frame().base + 1);
          }
          continue;
        }
        // The join condition and each additional predicate sit one level in,
        // under the clause they qualify.
        if (upper === 'ON' || upper === 'AND' || upper === 'OR') {
          open(frame().base + 1);
          append(token.text, false);
          previous = token;
          continue;
        }
      }

      // Default: one space, except immediately after `(` or `.`. Two adjacent
      // operators keep their space even though `= -1` reads better as one
      // unit: several dialects let a user define `=-` as an operator of its
      // own, and gluing them together would be a change of meaning rather
      // than a change of whitespace.
      append(token.text, !tightAfter);
      previous = token;
    }

    flush();

    // The select list, join conditions and predicates are indented one level
    // past their clause; `open()` above has already placed them.
    const formatted = lines.join('\n');
    return formatted.trim() ? formatted : source;
  } catch {
    return source;
  }
}
