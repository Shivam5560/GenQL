'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

const FINE_POINTER = '(pointer: fine)';
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

/**
 * Drives a few degrees of pointer-follow tilt on a single element.
 *
 * The angles are written straight onto the node as custom properties, so a
 * pointer move never re-renders React; `.gq-tilt` in `styles/motion.css` reads
 * them. The handlers are only returned when the environment actually wants the
 * effect — a fine pointer, and no reduced-motion preference — which means touch
 * devices get no listeners at all rather than a disabled one, and both media
 * queries are re-evaluated if the user changes them mid-session.
 */
export function usePointerTilt<T extends HTMLElement>(maxDegrees = 4) {
  const ref = useRef<T>(null);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const fine = window.matchMedia(FINE_POINTER);
    const reduced = window.matchMedia(REDUCED_MOTION);
    const sync = () => setEnabled(fine.matches && !reduced.matches);

    sync();
    fine.addEventListener('change', sync);
    reduced.addEventListener('change', sync);
    return () => {
      fine.removeEventListener('change', sync);
      reduced.removeEventListener('change', sync);
    };
  }, []);

  const reset = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty('--gq-tilt-x', '0deg');
    el.style.setProperty('--gq-tilt-y', '0deg');
  }, []);

  useEffect(() => {
    if (!enabled) reset();
  }, [enabled, reset]);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<T>) => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      // -0.5..0.5 from the element's centre, doubled to -1..1.
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
      el.style.setProperty('--gq-tilt-x', `${(-y * maxDegrees).toFixed(2)}deg`);
      el.style.setProperty('--gq-tilt-y', `${(x * maxDegrees).toFixed(2)}deg`);
    },
    [maxDegrees],
  );

  const tiltProps = enabled ? { onPointerMove, onPointerLeave: reset } : {};

  return { ref, tiltProps, enabled };
}
