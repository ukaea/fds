import type { LucideIcon } from 'lucide-react';
import { Cpu, Gauge, Sigma, SlidersHorizontal } from 'lucide-react';
import { ActivitySummary, ActivityType } from '@/lib/types';

// A label for each type of run, in the words someone looking for data would use.
const ORIGIN: Record<ActivityType, { label: string; icon: LucideIcon }> = {
  measurement: { label: 'Measured', icon: Gauge },
  analysis: { label: 'Analysed', icon: Sigma },
  simulation: { label: 'Simulated', icon: Cpu },
  calibration: { label: 'Calibration', icon: SlidersHorizontal },
};

export function originLabel(activity?: ActivitySummary | null): string | null {
  return activity?.activity_type ? ORIGIN[activity.activity_type].label : null;
}

/** The code behind a run and the version it ran at, such as "jintrac v220922". */
export function runName(activity?: ActivitySummary | null): string | null {
  if (!activity?.source) return null;
  return activity.source_version
    ? `${activity.source} ${activity.source_version}`
    : activity.source;
}

/**
 * How a record came about: measured, analysed or simulated, and by which code.
 *
 * One shot can hold two datasets with the same name, the reconstructed
 * equilibrium and a simulation's, and this is what tells their cards apart. A
 * measurement's source is the acquisition system, which says nothing a reader
 * needs, so only an analysis or a simulation names its code.
 */
export function RunBadge({ activity }: { activity?: ActivitySummary | null }) {
  if (!activity?.activity_type) return null;
  const { label, icon: Icon } = ORIGIN[activity.activity_type];
  const name = activity.activity_type === 'measurement' ? null : runName(activity);

  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-muted text-foreground rounded-full border border-border">
      <Icon className="w-3 h-3" aria-hidden />
      {label}
      {name && <span className="font-mono text-muted-foreground">{name}</span>}
    </span>
  );
}
