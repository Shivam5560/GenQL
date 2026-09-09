'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';

/**
 * Section-entrance reveal. Items in the same block pass an increasing `order`
 * so they arrive as a staggered set rather than all at once.
 *
 * The Keystone original used framer-motion's `whileInView`. This is an
 * IntersectionObserver and a CSS transition instead — GenQL has no motion
 * library and adding one for a fade would be a poor trade.
 *
 * Under `prefers-reduced-motion`, and in any environment without an observer,
 * the content is simply present from the start. It is never parked at
 * `opacity: 0` waiting for a callback that may not come.
 */
export function Reveal({
  children,
  className,
  order = 0,
  id,
}: {
  children: ReactNode;
  className?: string;
  order?: number;
  id?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(true);

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || typeof IntersectionObserver === 'undefined') return;
    const node = ref.current;
    if (!node) return;

    setShown(false);
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setShown(true);
        observer.disconnect();
      },
      { threshold: 0.15 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      id={id}
      className={`ks-reveal ${shown ? 'ks-reveal-in' : ''} ${className ?? ''}`}
      style={{ transitionDelay: `${order * 70}ms` }}
    >
      {children}
    </div>
  );
}
