import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// jsdom has no matchMedia implementation — every prefers-reduced-motion /
// pointer-fine gate in this app (usePointerTilt, the 3D auth backdrop, the
// theme provider) calls it on mount, so any test rendering those components
// needs this polyfill regardless of what the test itself asserts.
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

afterEach(() => {
  cleanup();
});
