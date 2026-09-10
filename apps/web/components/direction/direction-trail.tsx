'use client'

import { useEffect, useState } from 'react'
import { DIRECTION_STAGES } from './direction-stages'

const AUTO_ADVANCE_MS = 3200
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

export function DirectionTrail() {
  // Default to the ambiguity gate (index 3) — it's the most interesting stage to show first.
  const [activeIndex, setActiveIndex] = useState(3)
  useEffect(() => {
    if (window.matchMedia(REDUCED_MOTION).matches) return
    const id = setInterval(() => {
      setActiveIndex((i) => (i + 1) % DIRECTION_STAGES.length)
    }, AUTO_ADVANCE_MS)
    return () => clearInterval(id)
  }, [])

  const active = DIRECTION_STAGES[activeIndex]

  return (
    <section id="trail" className="border-t border-[var(--line)] px-6 py-16 md:px-10 md:py-24">
      <div className="mx-auto max-w-[1400px]">
        <div className="flex flex-wrap items-start justify-between gap-8">
          <div>
            <div className="font-eyebrow text-[10px] uppercase tracking-[0.2em] text-[var(--mute)]">
              01 — THE TRAIL
            </div>
            <h2 className="font-serif text-[clamp(2rem,4vw,3.6rem)] font-light leading-tight tracking-[-0.02em] mt-4">
              Every answer
              <br />
              <span className="italic text-[var(--mute)] font-extralight">shows its work.</span>
            </h2>
          </div>
          <p className="max-w-[42ch] text-[var(--mute)] text-[1.05rem] leading-relaxed">
            The spine is the whole turn at a glance. Click any stage for the evidence it produced —
            so when a query is wrong you fix the stage, not the prompt.
          </p>
        </div>

        <div className="mt-10 border border-[var(--line)] bg-[var(--panel)]">
          <div className="overflow-x-auto">
            <div className="grid grid-cols-12 min-w-[900px]">
              {DIRECTION_STAGES.map((stage, i) => {
                const isActive = i === activeIndex
                const isPast = i < activeIndex
                return (
                  <button
                    key={stage.code}
                    type="button"
                    onClick={() => setActiveIndex(i)}
                    className="border-r border-[var(--line)]/40 last:border-r-0 px-3 py-4 text-left"
                  >
                    <div
                      className={
                        'h-0.5 w-full ' +
                        (isActive
                          ? 'bg-[var(--brand)] gq-pulse'
                          : isPast
                            ? 'bg-[var(--ok)]'
                            : 'bg-[var(--line)]')
                      }
                    />
                    <div className="font-mono text-[0.65rem] text-[var(--mute)] mt-3">
                      {stage.num}
                    </div>
                    <div
                      className={
                        'font-serif text-sm truncate mt-1 ' +
                        (isActive
                          ? 'text-[var(--ink)]'
                          : isPast
                            ? 'text-[var(--mute)]'
                            : 'text-[var(--mute)]/60')
                      }
                    >
                      {stage.label}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] border-t border-[var(--line)]">
            <div className="border-r border-[var(--line)] p-8 lg:p-11">
              <div className="flex items-center gap-3">
                <span className="font-mono text-[10px] tracking-[0.18em] text-[var(--brand)]">
                  STAGE {active.num}
                </span>
                <span className="font-mono text-[10px] tracking-[0.18em] text-[var(--mute)]">
                  {active.code}
                </span>
              </div>
              <h3 className="font-serif text-[clamp(1.75rem,3vw,2.75rem)] font-light mt-4">
                {active.label}
              </h3>
              <p className="max-w-[52ch] text-[var(--mute)] text-[1.05rem] leading-relaxed mt-4">
                {active.summary}
              </p>
              <div className="border-l-2 border-[var(--brand)] bg-[var(--brand)]/10 px-4 py-3 italic text-[1rem] mt-6">
                {active.note}
              </div>
            </div>

            <div className="bg-[var(--panel-2)] p-8 lg:p-11">
              <div className="font-eyebrow text-[9px] uppercase tracking-[0.2em] text-[var(--mute)]">
                EVIDENCE
              </div>
              <div className="mt-4">
                {active.detail.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex justify-between gap-3 border-b border-[var(--line)]/40 py-3 font-mono text-[0.72rem]"
                  >
                    <span className="text-[var(--mute)]">{key}</span>
                    <span className="text-[var(--ink)] text-right">{value}</span>
                  </div>
                ))}
              </div>
              <div className="flex justify-between font-mono text-[10px] tracking-[0.14em] text-[var(--mute)] mt-4">
                <span>ELAPSED {active.ms}</span>
                <span>
                  ● <span className="text-[var(--ok)]">{active.status}</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
