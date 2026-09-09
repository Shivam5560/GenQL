'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useState } from 'react';
import { AmbientField } from '@/components/hero/ambient-field';

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

const SchemaScene = dynamic(
  () => import('@/components/three/schema-scene').then((m) => m.SchemaScene),
  { ssr: false },
);

/**
 * Atmospheric 3D backdrop for the auth entry screens: a loose cluster of
 * schema panels drifting behind the login/signup form. Never the focal
 * point — the form stays legible and undistracted in front of it.
 *
 * `three` (~600KB) is kept out of the main bundle by loading `SchemaScene`
 * through `next/dynamic({ ssr: false })`; this wrapper is the only place
 * that imports it, so no chat/sidebar route pulls it in.
 *
 * Falls back to {@link AmbientField} — this app's existing 2D drift
 * treatment, already themed and already reduced-motion-safe — whenever
 * `prefers-reduced-motion: reduce` is set or WebGL turns out to be
 * unavailable (blocklisted driver, exhausted context budget, headless
 * environment). A user is never left with nothing.
 */
export function SchemaSceneBackdrop() {
  const [reducedMotion, setReducedMotion] = useState(true);
  const [webglFailed, setWebglFailed] = useState(false);
  const onUnavailable = useCallback(() => setWebglFailed(true), []);

  useEffect(() => {
    const query = window.matchMedia(REDUCED_MOTION);
    const sync = () => setReducedMotion(query.matches);
    sync();
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);

  const useScene = !reducedMotion && !webglFailed;

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {useScene ? <SchemaScene onUnavailable={onUnavailable} /> : <AmbientField />}
    </div>
  );
}
