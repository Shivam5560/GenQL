import type { CSSProperties } from 'react';

/**
 * Three soft `--brand` radial fields drifting behind the composer.
 *
 * Alpha is baked into the gradient stop rather than applied as element opacity
 * so the peak value is readable here: 0.12 / 0.09 / 0.07, all inside the range
 * where warm orange over `--bg` shifts luminance by well under a percent and
 * leaves text contrast untouched. There is no `filter: blur()` — a radial
 * gradient is already the blur, and blurring an animated layer would move it
 * off the compositor for nothing.
 */
const FIELDS: { key: string; drift: string; style: CSSProperties }[] = [
  {
    key: 'a',
    drift: 'gq-drift-a',
    style: {
      top: '-22%',
      left: '-10%',
      width: 'min(62vw, 880px)',
      height: 'min(62vw, 880px)',
      background:
        'radial-gradient(circle at center, color-mix(in srgb, var(--brand) 12%, transparent) 0%, transparent 68%)',
      ['--gq-drift-duration' as string]: '38s',
    },
  },
  {
    key: 'b',
    drift: 'gq-drift-b',
    style: {
      bottom: '-20%',
      right: '-12%',
      width: 'min(48vw, 680px)',
      height: 'min(48vw, 680px)',
      background:
        'radial-gradient(circle at center, color-mix(in srgb, var(--brand) 9%, transparent) 0%, transparent 70%)',
      ['--gq-drift-duration' as string]: '29s',
    },
  },
  {
    key: 'c',
    drift: 'gq-drift-c',
    style: {
      top: '38%',
      left: '46%',
      width: 'min(34vw, 460px)',
      height: 'min(34vw, 460px)',
      background:
        'radial-gradient(circle at center, color-mix(in srgb, var(--brand) 7%, transparent) 0%, transparent 72%)',
      ['--gq-drift-duration' as string]: '47s',
    },
  },
];

export function AmbientField() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {FIELDS.map((field) => (
        <span
          key={field.key}
          className={`gq-drift ${field.drift} absolute block rounded-full`}
          style={field.style}
        />
      ))}
    </div>
  );
}
