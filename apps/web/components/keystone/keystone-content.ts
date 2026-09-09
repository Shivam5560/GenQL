/**
 * Content and palette for GenQL's entry screen.
 *
 * Ported from the Keystone landing (Professional_Grade_RAG), same author, with
 * the copy rewritten for GenQL. The palette is deliberately literal rather
 * than the app's `--bg`/`--ink` tokens: this is a light-only paper-and-ink
 * composition that does not participate in the workspace's light/dark toggle,
 * and keeping the values in one place is what lets the WebGL scene and the DOM
 * agree on the same ink, paper, and bronze.
 */
export const KS = {
  paper: '#f3efe7',
  card: '#f7f4ee',
  raised: '#fbf9f5',
  sunk: '#efe9dd',
  grid: '#e6e0d3',
  ink: '#16181a',
  bronze: '#b0602f',
  /** Bronze lifted for legibility on the ink-dark method band. */
  bronzeOnInk: '#c97a44',
  /** Stone tone for the solid in the hero scene. */
  stone: '#e7e0d2',
} as const;

/**
 * The three numbers are the product's actual promises, not marketing figures.
 * Eight is the count of pipeline stages a turn runs through; zero is the
 * number of statements GenQL executes without being told to.
 */
export const HERO_STATS = [
  { value: '08', label: 'Stages per answer' },
  { value: '0', label: 'Auto-run queries' },
  { value: '100%', label: 'SQL shown first' },
] as const;

/** GenQL's real pipeline, stated as three stations rather than eight nodes. */
export const STATIONS = [
  {
    label: 'Station 01',
    title: 'Survey',
    body: 'Every schema is scanned, profiled, and projected into a graph — tables, columns, foreign keys, join paths, and the business domains they cluster into.',
  },
  {
    label: 'Station 02',
    title: 'Plan',
    body: 'Your question is linked to the objects that can answer it, planned in prose, then written as several candidate statements — each one validated before any of them is chosen.',
  },
  {
    label: 'Station 03',
    title: 'Attest',
    body: 'The chosen SQL is costed, shown to you in full, and executed only when you press Execute. Nothing runs on your warehouse unasked.',
  },
] as const;
