import type { CSSProperties } from 'react';

/**
 * The display-type moment of the app.
 *
 * The headline is the product's actual instruction, not a slogan, set at
 * display scale in IBM Plex Sans — the same family as the rest of the UI, so
 * the shift in register comes from scale, weight and tracking rather than from
 * a second typeface. The supporting line states the Execute gate in the same
 * words the button uses, because that promise is the reason to trust the tool.
 */
export function HeroHeadline() {
  return (
    <div>
      <h1
        className="gq-rise max-w-[13ch] text-[clamp(2.5rem,6.4vw,4.25rem)] font-semibold leading-[0.95] tracking-[-0.035em] text-balance"
        style={{ '--gq-delay': '90ms' } as CSSProperties}
      >
        Ask your warehouse a question.
      </h1>
      <p
        className="gq-rise mt-5 max-w-[52ch] text-[0.95rem] leading-relaxed text-[var(--mute)]"
        style={{ '--gq-delay': '170ms' } as CSSProperties}
      >
        GenQL writes the SQL and shows it to you first. Nothing runs until you press Execute.
      </p>
    </div>
  );
}
