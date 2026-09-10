'use client';

import type { CSSProperties, ReactNode } from 'react';
import { SchemaSceneBackdrop } from '@/components/three/schema-scene-backdrop';
import { usePointerTilt } from '@/lib/use-pointer-tilt';

const eyebrow = 'font-eyebrow text-[10px] uppercase tracking-[0.2em] text-[var(--mute)]';

const cta =
  'font-eyebrow text-[11px] uppercase tracking-[0.16em] px-7 py-3.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]';

const kw = 'text-[var(--brand)] font-medium';
const lit = 'text-[var(--ok)]';

/**
 * Elevation is tinted with `--brand` over a `--bg` core rather than drawn in
 * grey, so a card reads as lifted in both themes without introducing a colour
 * that is not a token.
 */
const cardShadow =
  '0 30px 80px -50px color-mix(in srgb, var(--brand) 55%, transparent), 0 18px 44px -30px color-mix(in srgb, var(--bg) 92%, transparent)';

function HeroCard({
  delay,
  // The surface is passed in rather than defaulted, so the inverted gate card
  // does not have to out-rank a base `bg-` utility it cannot reliably beat.
  surface,
  className = '',
  children,
}: {
  delay: string;
  surface: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`gq-rise border border-[var(--line)] p-5 ${surface} ${className}`}
      style={{ '--gq-delay': delay, boxShadow: cardShadow } as CSSProperties}
    >
      {children}
    </div>
  );
}

export function DirectionHero() {
  const { ref, tiltProps } = usePointerTilt<HTMLDivElement>();

  return (
    // `isolate` keeps the backdrop's `-z-10` inside this section instead of
    // dropping it behind the page ground.
    <div className="relative isolate overflow-hidden">
      <SchemaSceneBackdrop />
      {/* The 3D graph runs edge to edge; this scrim pulls --bg back over the
          reading column so the headline never competes with a moving node. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_90%_70%_at_30%_45%,var(--bg)_0%,transparent_78%)]"
      />

      <section className="relative mx-auto grid w-full max-w-[1200px] grid-cols-1 items-center gap-14 px-6 py-16 lg:grid-cols-[1.05fr_1fr] lg:gap-20 lg:px-10 lg:py-28">
        <div>
          <div
            className="gq-rise flex items-center gap-2.5"
            style={{ '--gq-delay': '90ms' } as CSSProperties}
          >
            <span className="gq-pulse size-1.5 rounded-full bg-[var(--brand)]" />
            <span className={eyebrow}>TEXT-TO-SQL, UNDER AUDIT</span>
          </div>

          <h1
            className="gq-rise mt-6 font-serif text-[clamp(2.75rem,6vw,5.5rem)] font-light leading-[0.95] tracking-[-0.03em]"
            style={{ '--gq-delay': '170ms' } as CSSProperties}
          >
            Ask in plain English.
            <br />
            <span className="font-light italic text-[var(--mute)]">Get SQL you can</span>
            <br />
            defend in review.
          </h1>

          <p
            className="gq-rise mt-7 max-w-[46ch] text-[1.05rem] leading-relaxed text-[var(--mute)]"
            style={{ '--gq-delay': '250ms' } as CSSProperties}
          >
            AuraSQL reads your question, links it to real tables, and asks before it assumes.
            It drafts a few candidate queries, checks them against your schema, and stops if the
            cost looks wrong. You get the query, and the reasoning behind it.
          </p>

          <div
            className="gq-rise mt-9 flex flex-wrap gap-3"
            style={{ '--gq-delay': '330ms' } as CSSProperties}
          >
            <a
              href="#trail"
              className={`${cta} bg-[var(--brand)] text-[var(--brand-ink)] hover:opacity-90`}
            >
              Walk the trail
            </a>
            <a
              href="https://github.com/Shivam5560/GenQL"
              className={`${cta} border border-[var(--line)] text-[var(--ink)] hover:border-[var(--brand)] hover:text-[var(--brand)]`}
            >
              Run it locally
            </a>
          </div>
        </div>

        {/* Tilt lives on the wrapper, not each card: one shared perspective is
            what makes the three read as a single deck rather than three
            independently hinged panels. */}
        <div ref={ref} {...tiltProps} className="gq-tilt relative">
          <HeroCard delay="430ms" surface="bg-[var(--panel)]">
            <p className={eyebrow}>PROMPT</p>
            <p className="mt-3 font-serif text-xl leading-snug">
              Top 5 states by distinct stores since Jan 2020
              <span aria-hidden className="gq-pulse ml-1 inline-block h-[1.1em] w-px align-middle bg-[var(--brand)]" />
            </p>
          </HeroCard>

          <HeroCard delay="520ms" surface="bg-[var(--panel)]" className="-mt-4 ml-5">
            <div className="flex items-center justify-between gap-4">
              <span className={eyebrow}>GENERATED SQL</span>
              <span className="font-eyebrow text-[10px] uppercase tracking-[0.16em] text-[var(--ok)]">
                ● Validated
              </span>
            </div>
            <pre className="mt-4 overflow-x-auto font-mono text-[0.8rem] leading-relaxed">
              <span className={kw}>SELECT</span>
              {'\n  s.s_state '}
              <span className={kw}>AS</span>
              {' state,\n  '}
              <span className={kw}>COUNT</span>
              {'('}
              <span className={kw}>DISTINCT</span>
              {' s.s_store_id) '}
              <span className={kw}>AS</span>
              {' distinct_store_count\n'}
              <span className={kw}>FROM</span>
              {' tpcds.store '}
              <span className={kw}>AS</span>
              {' s\n'}
              <span className={kw}>WHERE</span>
              {' s.s_rec_start_date <= '}
              <span className={kw}>CURRENT_DATE</span>
              {'\n  '}
              <span className={kw}>AND</span>
              {' (s.s_rec_end_date >= '}
              <span className={lit}>{"'2020-01-01'"}</span>
              {' '}
              <span className={kw}>OR</span>
              {' s.s_rec_end_date '}
              <span className={kw}>IS NULL</span>
              {')\n'}
              <span className={kw}>GROUP BY</span>
              {' s.s_state\n'}
              <span className={kw}>ORDER BY</span>
              {' distinct_store_count '}
              <span className={kw}>DESC</span>
              {'\n'}
              <span className={kw}>LIMIT</span>
              {' '}
              <span className={lit}>5</span>
            </pre>
            <div className="mt-4 flex items-center justify-between gap-4 border-t border-[var(--line)] pt-3 font-eyebrow text-[0.68rem] uppercase tracking-[0.14em] text-[var(--mute)]">
              <span>5 ROWS · 41 MS · 12 KB SCANNED</span>
              <span>COPY</span>
            </div>
          </HeroCard>

          <HeroCard
            delay="610ms"
            surface="bg-[var(--ink)] text-[var(--bg)]"
            className="-mt-4 ml-10"
          >
            <p className="font-eyebrow text-[10px] uppercase tracking-[0.2em] opacity-60">
              AMBIGUITY GATE
            </p>
            <p className="mt-3 font-serif text-[1.05rem] italic leading-snug">
              &ldquo;Distinct on stores, or on states?&rdquo;
            </p>
          </HeroCard>
        </div>
      </section>
    </div>
  );
}
