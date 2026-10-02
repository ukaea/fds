'use client';

import { useId } from 'react';

// Marks a name that has a description to read.
export const DESCRIBED =
  'cursor-help underline decoration-dotted decoration-muted-foreground underline-offset-2';

/**
 * A property name, with what it means on hover or focus when the provider has
 * said. The dotted underline is the cue that there is something to read.
 *
 * Focusable, so a keyboard user reaches the description too; CSS rather than
 * `title`, which never shows on focus and only after a delay on hover.
 */
export function DescribedName({
  name,
  description,
  className = '',
}: {
  name: string;
  description?: string | null;
  className?: string;
}) {
  const id = useId();
  if (!description) return <span className={className}>{name}</span>;
  return (
    <span className="relative inline-block group">
      <span
        tabIndex={0}
        aria-describedby={id}
        className={`${className} ${DESCRIBED} rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary`}
      >
        {name}
      </span>
      <span
        role="tooltip"
        id={id}
        className="pointer-events-none absolute left-0 top-full z-20 mt-1 w-64 rounded-md border border-border bg-card px-2.5 py-1.5 text-[11px] font-normal normal-case tracking-normal leading-snug text-foreground shadow-lg invisible opacity-0 transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        {description}
      </span>
    </span>
  );
}
