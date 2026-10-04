'use client';

import { type ReactNode, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

// The body is rendered only while open, so what it loads waits for the reader.
export function CollapsibleSection({
  label,
  hint,
  defaultOpen = false,
  className = 'card overflow-hidden',
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={className}>
      <div className="flex items-center gap-2 px-4 py-2.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex items-center gap-2 text-sm text-foreground font-medium hover:text-primary transition-colors"
        >
          {open ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          {label}
        </button>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
      {open && <div className="border-t border-border p-4">{children}</div>}
    </div>
  );
}
