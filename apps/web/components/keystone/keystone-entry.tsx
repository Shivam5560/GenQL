'use client';

import { useState } from 'react';
import { HERO_STATS, STATIONS } from '@/components/keystone/keystone-content';
import { Reveal } from '@/components/keystone/reveal';
import { TriangulationSolid } from '@/components/keystone/triangulation-solid';
import { AuthPanel, type AuthMode } from '@/components/keystone/auth-panel';

// Plate grain, laid over everything and multiplied into the paper so the flat
// background reads as stock rather than as a filled rectangle.
const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/></filter><rect width='160' height='160' filter='url(%23n)'/></svg>\")";

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#b0602f] focus-visible:ring-offset-2 focus-visible:ring-offset-[#f3efe7]';

const navLink = `text-[#16181a]/60 transition-colors hover:text-[#16181a] ${focusRing}`;
const mono = { fontFamily: 'var(--font-eyebrow)' } as const;

/**
 * GenQL's entry screen, ported from the Keystone landing.
 *
 * Deliberately light-only: this is a paper-and-ink composition that does not
 * follow the workspace's light/dark toggle, so every colour here is a literal
 * from `keystone-content.ts` rather than a `--bg`/`--ink` token. It paints its
 * own background explicitly, so it holds on either host theme.
 *
 * Both `/login` and `/signup` render this; the route decides which mode the
 * panel opens in, and the panel is a real dialog rather than a separate page
 * so the composition stays behind it.
 */
export function KeystoneEntry({
  initialMode,
  openOnMount = false,
}: {
  initialMode: AuthMode;
  /** `/signup` is a direct request for the form, so it opens on it. */
  openOnMount?: boolean;
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [open, setOpen] = useState(openOnMount);

  function openAuth(next: AuthMode) {
    setMode(next);
    setOpen(true);
  }

  return (
    <div
      className="relative min-h-screen overflow-x-hidden bg-[#f3efe7] text-[#16181a] antialiased"
      style={{ fontWeight: 350 }}
    >
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-[80] opacity-[0.055] mix-blend-multiply"
        style={{ backgroundImage: GRAIN }}
      />

      <header className="fixed inset-x-0 top-0 z-50 flex items-center justify-between gap-6 border-b border-[#16181a]/[0.07] bg-gradient-to-b from-[#f3efe7]/95 to-[#f3efe7]/60 px-6 py-[18px] backdrop-blur-[14px] md:px-10 md:py-[22px]">
        <a href="/login" className={`flex items-center gap-3.5 ${focusRing}`}>
          <span
            aria-hidden
            className="relative block h-[15px] w-[15px] rotate-45 border-[1.5px] border-[#16181a]"
          >
            <span className="absolute inset-[3.5px] bg-[#b0602f]" />
          </span>
          <span className="font-serif text-[20px] tracking-[0.02em]">GenQL</span>
          <span
            className="hidden border-l border-[#16181a]/15 pl-1.5 text-[10px] uppercase tracking-[0.18em] text-[#16181a]/40 sm:inline"
            style={mono}
          >
            Warehouse engine
          </span>
        </a>

        <nav
          aria-label="Entry"
          className="flex items-center gap-4 text-[11px] uppercase tracking-[0.12em] md:gap-8"
          style={mono}
        >
          <a className={`hidden md:inline ${navLink}`} href="#method">
            Method
          </a>
          <button type="button" className={navLink} onClick={() => openAuth('login')}>
            Log in
          </button>
          <button
            type="button"
            onClick={() => openAuth('register')}
            className={`flex items-center gap-2.5 whitespace-nowrap bg-[#16181a] px-3 py-2.5 text-[10px] uppercase tracking-[0.08em] text-[#f7f4ee] transition-colors hover:bg-[#2c2f32] md:px-4 md:text-[11px] md:tracking-[0.14em] ${focusRing}`}
          >
            Request access
            <span aria-hidden className="h-[5px] w-[5px] bg-[#b0602f]" />
          </button>
        </nav>
      </header>

      <main>
        <section
          id="survey"
          className="relative mx-auto grid max-w-[1560px] items-center gap-8 px-6 pb-16 pt-32 md:px-10 md:pb-20 md:pt-[150px] lg:min-h-screen lg:grid-cols-[1.02fr_1fr] lg:gap-5"
        >
          <div className="relative z-[2] max-w-[640px]">
            <Reveal
              className="mb-6 flex items-center gap-4 text-[11px] uppercase tracking-[0.2em] text-[#16181a]/45 md:mb-[34px]"
            >
              <span style={mono} className="flex items-center gap-4">
                <span className="text-[#b0602f]">01</span>
                <span aria-hidden className="h-px w-[52px] bg-[#16181a]/20" />
                <span>One engine, every warehouse</span>
              </span>
            </Reveal>

            <Reveal order={1}>
              <h1 className="mb-7 font-serif text-[clamp(52px,7.4vw,116px)] font-normal leading-[0.92] tracking-[-0.028em] md:mb-[30px]">
                Questions,
                <br />
                <em className="font-light text-[#b0602f]">compiled.</em>
              </h1>
            </Reveal>

            <Reveal order={2}>
              <p className="mb-9 max-w-[452px] text-pretty text-[17px] leading-[1.6] text-[#16181a]/[0.66] md:mb-11 md:text-[19px]">
                GenQL surveys your schema, plans a route through it, and writes the SQL — then
                shows you the statement before anything runs. Answers you can read, edit, and
                defend.
              </p>
            </Reveal>

            <Reveal order={3} className="mb-12 flex flex-wrap items-center gap-3.5 md:mb-16">
              <button
                type="button"
                onClick={() => openAuth('login')}
                className={`flex items-center gap-3 bg-[#16181a] px-6 py-4 text-[11px] uppercase tracking-[0.16em] text-[#f7f4ee] transition-colors hover:bg-[#2c2f32] ${focusRing}`}
                style={mono}
              >
                Sign in
                <span aria-hidden className="h-1.5 w-1.5 bg-[#b0602f]" />
              </button>
              <a
                className={`flex items-center gap-2.5 border border-[#16181a]/20 px-[22px] py-4 text-[11px] uppercase tracking-[0.16em] text-[#16181a]/70 transition-colors hover:border-[#16181a]/45 hover:text-[#16181a] ${focusRing}`}
                style={mono}
                href="#method"
              >
                Read the method
              </a>
            </Reveal>

            <Reveal order={4}>
              <dl className="grid max-w-[520px] grid-cols-3 border-t border-[#16181a]/[0.14]">
                {HERO_STATS.map((stat, index) => (
                  <div
                    key={stat.label}
                    className={`pt-[18px] ${index === 0 ? 'pr-5' : index === 1 ? 'px-5' : 'pl-5'} ${
                      index < HERO_STATS.length - 1 ? 'border-r border-[#16181a]/10' : ''
                    }`}
                  >
                    <dd className="font-serif text-[28px] leading-none md:text-[34px]">
                      {stat.value}
                    </dd>
                    <dt
                      className="mt-1.5 text-[10px] uppercase leading-[1.4] tracking-[0.14em] text-[#16181a]/45"
                      style={mono}
                    >
                      {stat.label}
                    </dt>
                  </div>
                ))}
              </dl>
            </Reveal>
          </div>

          <figure className="relative z-[1] m-0">
            <TriangulationSolid />
          </figure>
        </section>

        <section
          id="method"
          className="border-t border-[#16181a]/[0.09] bg-[#efe9dd] px-6 py-20 md:px-10 md:py-28"
        >
          <div className="mx-auto max-w-[1200px]">
            <Reveal
              className="mb-12 flex items-center gap-4 text-[11px] uppercase tracking-[0.2em] text-[#16181a]/45"
            >
              <span style={mono} className="flex items-center gap-4">
                <span className="text-[#b0602f]">02</span>
                <span aria-hidden className="h-px w-[52px] bg-[#16181a]/20" />
                <span>The method</span>
              </span>
            </Reveal>
            <div className="grid gap-px bg-[#16181a]/10 md:grid-cols-3">
              {STATIONS.map((station, index) => (
                <Reveal key={station.title} order={index} className="bg-[#efe9dd] p-7 md:p-9">
                  <p
                    className="text-[10px] uppercase tracking-[0.16em] text-[#16181a]/40"
                    style={mono}
                  >
                    {station.label}
                  </p>
                  <h3 className="mt-4 font-serif text-[30px] leading-none tracking-[-0.02em] md:text-[36px]">
                    {station.title}
                  </h3>
                  <p className="mt-4 max-w-[42ch] text-[15px] leading-[1.65] text-[#16181a]/[0.66]">
                    {station.body}
                  </p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="flex flex-wrap items-center justify-between gap-4 border-t border-[#16181a]/[0.09] px-6 py-8 text-[10px] uppercase tracking-[0.16em] text-[#16181a]/40 md:px-10">
        <span style={mono}>GenQL — natural language to SQL</span>
        <button
          type="button"
          onClick={() => openAuth('login')}
          className={`${navLink} uppercase tracking-[0.16em]`}
          style={mono}
        >
          Log in
        </button>
      </footer>

      {open && (
        <AuthPanel mode={mode} onModeChange={setMode} onClose={() => setOpen(false)} />
      )}
    </div>
  );
}
