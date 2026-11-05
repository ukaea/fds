import type { LucideIcon } from 'lucide-react';
import { Cpu, Gauge, Sigma, SlidersHorizontal } from 'lucide-react';
import { ActivitySummary, ActivityType } from '@/lib/types';

// A label for each type of Activity, in the words someone looking for data would use.
const ORIGIN: Record<ActivityType, { label: string; icon: LucideIcon }> = {
  measurement: { label: 'Measured', icon: Gauge },
  analysis: { label: 'Analysed', icon: Sigma },
  simulation: { label: 'Simulated', icon: Cpu },
  calibration: { label: 'Calibration', icon: SlidersHorizontal },
};

// A full git commit hash is cut to the seven characters git itself shows. Any
// other version is shown as recorded.
function shortVersion(version: string): string {
  return /^[0-9a-f]{40}$/i.test(version) ? version.slice(0, 7) : version;
}

/** The code behind an Activity and the version it ran at, such as "jintrac v220922". */
export function activityName(activity?: ActivitySummary | null): string | null {
  if (!activity?.source) return null;
  return activity.source_version
    ? `${activity.source} ${shortVersion(activity.source_version)}`
    : activity.source;
}

/** The day an Activity started, such as "3 Oct 2026". */
export function activityDate(activity?: ActivitySummary | null): string | null {
  if (!activity?.started_at) return null;
  return new Date(activity.started_at).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

// What the badge says about an Activity. A measurement's source is the
// acquisition system and its date is the shot's, neither of which tells a reader
// anything, so a measurement is given only its label.
function describe(type: ActivityType, activity: ActivitySummary) {
  const measured = type === 'measurement';
  return {
    ...ORIGIN[type],
    name: measured ? null : activityName(activity),
    date: measured ? null : activityDate(activity),
    fullName: measured ? null : [activity.source, activity.source_version].filter(Boolean).join(' '),
  };
}

/**
 * How a record came about: measured, analysed or simulated, by which code, and
 * when it ran.
 *
 * One shot can hold several datasets with the same name, such as a reconstructed
 * equilibrium and the equilibria of two simulation runs, and this is what tells
 * their cards apart. Two Activities of the same code at the same version differ only in
 * when they ran, so the start date is shown as well.
 */
export function ActivityBadge({ activity }: { activity?: ActivitySummary | null }) {
  if (!activity?.activity_type) return null;
  const { label, icon: Icon, name, date, fullName } = describe(activity.activity_type, activity);

  // Laid out as text rather than flex so a badge too long for its card wraps
  // between words, with the separator kept at the end of the first line. The
  // hover text has the version in full, since the badge may shorten it.
  return (
    <span
      className="inline-block max-w-full text-xs px-2 py-0.5 bg-muted text-foreground rounded-xl border border-border wrap-anywhere"
      title={fullName || undefined}
    >
      <Icon className="inline w-3 h-3 mr-1 align-[-0.125em]" aria-hidden />
      {label}
      {name && <> <span className="font-mono text-muted-foreground">{name}</span></>}
      {date && (
        <>
          {'\u00a0'}<span className="px-0.5">·</span> <span className="text-muted-foreground whitespace-nowrap">{date}</span>
        </>
      )}
    </span>
  );
}
