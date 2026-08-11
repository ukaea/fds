'use client';

import type { LucideIcon } from 'lucide-react';
import { Dataset } from '@/lib/types';
import { ResolvedRef } from '@/components/resolved-ref';

// One kind of dataset resolved for a subject — a geometry role, a calibration
// chain, or the feature annotations. `hint` carries the qualifier that makes the
// group readable: the order a chain applies in, or the frame a set is expressed
// in. Renders nothing when the subject has none of that kind.
export function RelatedGroup({
  icon: Icon,
  label,
  hint,
  datasets,
}: {
  icon: LucideIcon;
  label: string;
  hint?: string;
  datasets?: Dataset[];
}) {
  if (!datasets || datasets.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2 text-muted-foreground uppercase text-xs font-bold tracking-wider">
        <Icon className="w-4 h-4" />
        {label}
        {hint && <span className="normal-case font-normal text-muted-foreground">{hint}</span>}
      </div>
      <div className="space-y-2">
        {datasets.map((dataset) => (
          <ResolvedRef key={dataset.id} version={dataset} />
        ))}
      </div>
    </div>
  );
}
