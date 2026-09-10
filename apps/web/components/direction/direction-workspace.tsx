import { Fragment } from 'react';

const THREADS = [
  { title: 'Top 5 states with number of distinct stores', active: true },
  { title: 'Top stores in terms of sales list down…', active: false },
  { title: 'Finds customers in a high income bracket', active: false },
  { title: 'Customer who has most orders ?', active: false },
  { title: 'Churn Prediction ?', active: false },
];

export function DirectionWorkspace() {
  return (
    <section id="workspace" className="border-t border-[var(--line)] px-6 py-16 md:px-10 md:py-24">
      <div className="mx-auto max-w-[1400px]">
        <div className="flex flex-wrap items-end justify-between gap-9">
          <div>
            <span className="font-eyebrow text-[10px] uppercase tracking-[0.2em] text-[var(--mute)]">
              02 — THE WORKSPACE
            </span>
            <h2 className="mt-4 font-serif text-[clamp(2rem,4vw,3.6rem)] font-light leading-tight tracking-[-0.02em]">
              The spine moves up.{' '}
              <span className="font-extralight italic text-[var(--mute)]">The rail is gone.</span>
            </h2>
          </div>
          <p className="max-w-[42ch] text-[1.05rem] leading-relaxed text-[var(--mute)]">
            A 212px rail forced twelve stages into a column nobody reads. Above the answer, the
            same twelve become a progress bar you can interrogate, and the query gets the full
            width.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 overflow-hidden border border-[var(--line)] bg-[var(--panel)] shadow-2xl md:grid-cols-[216px_1fr]">
          <div className="hidden flex-col border-r border-[var(--line)] bg-[var(--panel-2)] md:flex">
            <div className="m-3.5 bg-[var(--brand)] py-2.5 text-center font-mono text-[10px] tracking-[0.16em] text-[var(--brand-ink)]">
              + New thread
            </div>
            <div className="px-3.5 pb-3">
              <p className="text-[13px] text-[var(--mute)]">Datasource</p>
              <div className="mt-1.5 flex items-center justify-between border border-[var(--line)] px-2.5 py-1.5 text-[13px]">
                <span className="truncate">ambiguity_example_ds</span>
                <span aria-hidden className="text-[var(--mute)]">
                  ⌄
                </span>
              </div>
            </div>
            <div className="px-3.5 pb-3">
              <p className="text-[13px] text-[var(--mute)]">Threads</p>
              <ul className="mt-1.5 flex flex-col gap-1.5">
                {THREADS.map((t) => (
                  <li
                    key={t.title}
                    className={`truncate px-2 py-1.5 text-[13px] ${
                      t.active
                        ? 'border-l-2 border-[var(--brand)] font-semibold text-[var(--ink)]'
                        : 'border-l-2 border-transparent text-[var(--mute)]'
                    }`}
                  >
                    {t.title}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div>
            <div className="grid grid-cols-12 border-b border-[var(--line)] bg-[var(--panel-2)]">
              {Array.from({ length: 12 }).map((_, i) => (
                <div
                  key={i}
                  className={`h-0.5 ${i === 11 ? 'bg-[var(--brand)]' : 'bg-[var(--ok)]'}`}
                />
              ))}
            </div>

            <div className="p-6 md:p-10">
              <h3 className="max-w-[26ch] font-serif text-2xl font-light md:text-3xl">
                Top 5 states with number of distinct stores since 1 Jan 2020
              </h3>

              <div className="mt-6 border border-[var(--line)]">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] bg-[var(--panel-2)] px-4 py-3">
                  <span className="flex items-center gap-3">
                    <span className="font-eyebrow text-[10px] uppercase tracking-[0.16em] text-[var(--mute)]">
                      GENERATED SQL
                    </span>
                    <span className="text-[0.8rem] text-[var(--ok)]">● Validated</span>
                  </span>
                  <span className="flex items-center gap-3 font-eyebrow text-[10px] uppercase tracking-[0.16em] text-[var(--mute)]">
                    <span>Postgres</span>
                    <span>Copy</span>
                  </span>
                </div>
                <pre className="overflow-x-auto p-4 font-mono text-[0.78rem] leading-relaxed">
                  <span className="text-[var(--brand)] font-medium">SELECT</span> s.s_state{' '}
                  <span className="text-[var(--brand)] font-medium">AS</span> state,{' '}
                  <span className="text-[var(--brand)] font-medium">COUNT</span>(
                  <span className="text-[var(--brand)] font-medium">DISTINCT</span> s.s_store_id){' '}
                  <span className="text-[var(--brand)] font-medium">AS</span>{' '}
                  distinct_store_count
                  {'\n'}
                  <span className="text-[var(--brand)] font-medium">FROM</span> tpcds.store{' '}
                  <span className="text-[var(--brand)] font-medium">AS</span> s{'\n'}
                  <span className="text-[var(--brand)] font-medium">GROUP BY</span> s.s_state{' '}
                  <span className="text-[var(--brand)] font-medium">ORDER BY</span>{' '}
                  distinct_store_count{' '}
                  <span className="text-[var(--brand)] font-medium">DESC</span>{' '}
                  <span className="text-[var(--brand)] font-medium">LIMIT</span>{' '}
                  <span className="text-[var(--ok)]">5</span>
                </pre>
                <div className="grid grid-cols-3 border-t border-[var(--line)] font-mono text-[11px]">
                  <div className="border-b border-[var(--line)]/40 px-3 py-2 uppercase text-[var(--mute)]">
                    #
                  </div>
                  <div className="border-b border-[var(--line)]/40 px-3 py-2 uppercase text-[var(--mute)]">
                    State
                  </div>
                  <div className="border-b border-[var(--line)]/40 px-3 py-2 text-right uppercase text-[var(--mute)]">
                    Distinct_Stores
                  </div>
                  {[
                    ['1', 'TN', '6'],
                    ['2', 'SD', '4'],
                    ['3', 'MI', '3'],
                    ['4', 'NE', '2'],
                    ['5', 'TX', '2'],
                  ].map(([n, state, count]) => (
                    <Fragment key={n}>
                      <div className="border-b border-[var(--line)]/40 px-3 py-2">{n}</div>
                      <div className="border-b border-[var(--line)]/40 px-3 py-2">{state}</div>
                      <div className="border-b border-[var(--line)]/40 px-3 py-2 text-right">
                        {count}
                      </div>
                    </Fragment>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-4 py-3">
                  <span className="font-mono text-[10px] text-[var(--mute)]">
                    5 ROWS · DOWNLOAD CSV
                  </span>
                  <span className="flex items-center gap-2.5">
                    <span className="font-mono text-[10px] text-[var(--mute)]">
                      WAS THIS RIGHT?
                    </span>
                    <span className="border border-[var(--line)] px-2.5 py-1 text-[10px]">
                      YES
                    </span>
                    <span className="border border-[var(--line)] px-2.5 py-1 text-[10px] text-[var(--mute)]">
                      NOT QUITE
                    </span>
                  </span>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border border-[var(--line)] px-4 py-3.5">
                <span className="text-[var(--mute)]">Ask a follow-up about local…</span>
                <span className="font-mono text-[10px] tracking-[0.16em] text-[var(--brand)]">
                  SEND ↵
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
