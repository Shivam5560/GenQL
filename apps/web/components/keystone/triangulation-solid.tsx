'use client';

import dynamic from 'next/dynamic';
import { useCallback, useState } from 'react';
import { KS } from '@/components/keystone/keystone-content';
import { useCinematicEffects } from '@/lib/use-cinematic-effects';

const TriangulationScene = dynamic(
  () =>
    import('@/components/keystone/triangulation-scene').then((m) => m.TriangulationScene),
  { ssr: false },
);

/**
 * Hero figure. Renders the WebGL solid where the device can afford it and a
 * flat plate drawing of the same instrument everywhere else — reduced motion,
 * coarse pointers, save-data, and low-memory devices all fall back rather than
 * degrade, and so does a browser that cannot give us a context at all.
 *
 * `three` is ~600KB and is kept out of every other route's bundle by loading
 * the scene through `next/dynamic({ ssr: false })`; this file is the only
 * thing that imports it.
 */
export function TriangulationSolid() {
  const { enabled } = useCinematicEffects();
  const [webglFailed, setWebglFailed] = useState(false);
  const onUnavailable = useCallback(() => setWebglFailed(true), []);

  return (
    <div className="relative h-[46vh] min-h-[300px] w-full lg:-ml-[8%] lg:h-[min(84vh,780px)]">
      {enabled && !webglFailed ? (
        <TriangulationScene onUnavailable={onUnavailable} />
      ) : (
        <TriangulationPlate />
      )}
      <figcaption
        className="absolute bottom-2 left-0 flex items-center gap-4 text-[10px] uppercase tracking-[0.16em] lg:bottom-[34px]"
        style={{ fontFamily: 'var(--font-eyebrow)', color: 'rgba(22,24,26,0.35)' }}
      >
        <span>Fig. 01 — Schema solid</span>
        <span aria-hidden className="hidden h-px w-[26px] lg:block" style={{ background: 'rgba(22,24,26,0.2)' }} />
        <span className="hidden lg:inline">Cursor to orient</span>
      </figcaption>
    </div>
  );
}

/** Static engraving of the solid: nine courses, two dials, three bearings, bronze core. */
function TriangulationPlate() {
  const courses = Array.from({ length: 9 }, (_, i) => {
    const t = i / 8;
    return { half: 120 - t * 88, y: 300 - i * 26 };
  });

  return (
    <svg
      aria-hidden
      viewBox="0 0 400 400"
      className="absolute inset-0 h-full w-full"
      fill="none"
      preserveAspectRatio="xMidYMid meet"
    >
      <ellipse cx="200" cy="196" rx="150" ry="52" stroke={KS.ink} strokeOpacity="0.18" />
      <ellipse
        cx="200"
        cy="196"
        rx="150"
        ry="52"
        stroke={KS.ink}
        strokeOpacity="0.14"
        transform="rotate(34 200 196)"
      />
      {courses.map((course) => (
        <path
          key={course.y}
          d={`M${200 - course.half} ${course.y} L${200 - course.half * 0.5} ${course.y - 17} L${200 + course.half * 0.5} ${course.y - 17} L${200 + course.half} ${course.y} L${200 + course.half * 0.5} ${course.y + 17} L${200 - course.half * 0.5} ${course.y + 17} Z`}
          fill={KS.stone}
          stroke={KS.ink}
          strokeOpacity="0.28"
        />
      ))}
      {/* The three bearings, drawn over the stack so the concept stays visible. */}
      {[0, 120, 240].map((angle) => (
        <rect
          key={angle}
          x="196"
          y="144"
          width="8"
          height="52"
          fill={KS.bronze}
          transform={`rotate(${angle + 23} 200 196)`}
        />
      ))}
      <path
        d="M200 46 L226 66 L216 98 L184 98 L174 66 Z"
        fill={KS.bronze}
        stroke={KS.ink}
        strokeOpacity="0.35"
      />
    </svg>
  );
}
