'use client';

import { useEffect, useState } from 'react';

interface NavigatorHints extends Navigator {
  connection?: { saveData?: boolean };
  deviceMemory?: number;
}

/**
 * Whether this device should be given the WebGL treatment.
 *
 * Four independent reasons to say no, and any one of them is enough: the
 * visitor asked for reduced motion, the pointer is coarse (a phone, where the
 * pointer-driven scene has nothing to answer to and the battery cost is
 * real), the connection is metered, or the device is low on memory. Ported
 * from the Keystone landing along with the scene it gates.
 */
export function shouldEnableCinematicEffects(hints: {
  reducedMotion: boolean;
  coarsePointer: boolean;
  saveData: boolean;
  deviceMemory?: number;
}): boolean {
  if (hints.reducedMotion || hints.coarsePointer || hints.saveData) return false;
  return hints.deviceMemory === undefined || hints.deviceMemory >= 4;
}

function readState() {
  const hints = navigator as NavigatorHints;
  return {
    enabled: shouldEnableCinematicEffects({
      reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
      coarsePointer: matchMedia('(pointer: coarse)').matches,
      saveData: hints.connection?.saveData === true,
      deviceMemory: hints.deviceMemory,
    }),
    visible: document.visibilityState === 'visible',
  };
}

export function useCinematicEffects() {
  // Starts disabled so the server-rendered markup and the first client render
  // agree: the flat plate is what both draw, and the scene replaces it only
  // after the capability check has actually run.
  const [state, setState] = useState({ enabled: false, visible: true });

  useEffect(() => {
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const coarse = matchMedia('(pointer: coarse)');
    const update = () => setState(readState());

    update();
    reduced.addEventListener('change', update);
    coarse.addEventListener('change', update);
    document.addEventListener('visibilitychange', update);

    return () => {
      reduced.removeEventListener('change', update);
      coarse.removeEventListener('change', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, []);

  return state;
}
