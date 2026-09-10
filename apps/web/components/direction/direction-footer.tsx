export function DirectionFooter() {
  return (
    <footer className="border-t border-[var(--line)] px-6 py-16 md:px-10 md:py-24">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-end justify-between gap-9">
        <div>
          <div className="font-serif text-[clamp(2rem,4.2vw,4.5rem)] font-light leading-[1.02] tracking-[-0.02em]">
            Run it on your
            <br />
            <span className="font-extralight italic text-[var(--mute)]">own warehouse.</span>
          </div>
          <a
            href="https://github.com/Shivam5560/GenQL"
            className="mt-7 inline-block bg-[var(--brand)] px-7 py-3.5 font-eyebrow text-[11px] uppercase tracking-[0.16em] text-[var(--brand-ink)]"
          >
            github.com/Shivam5560/GenQL
          </a>
        </div>
        <div className="flex flex-col gap-1.5 font-eyebrow text-[9px] uppercase tracking-[0.16em] text-[var(--mute)]">
          <span>
            Gen<span className="text-[var(--brand)]">QL</span>
          </span>
          <span>Obsidian &amp; copper · ink &amp; ivory</span>
        </div>
      </div>
    </footer>
  );
}
