import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import { ChevronRight, Cpu, Gauge, Sigma, SlidersHorizontal } from 'lucide-react';
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

// A full git commit hash is cut to the seven characters git itself shows. Any
// other version is shown as recorded.
function shortVersion(version: string): string {
  return /^[0-9a-f]{40}$/i.test(version) ? version.slice(0, 7) : version;
}

/** The code behind a run and the version it ran at, such as "jintrac v220922". */
export function runName(activity?: ActivitySummary | null): string | null {
  if (!activity?.source) return null;
  return activity.source_version
    ? `${activity.source} ${shortVersion(activity.source_version)}`
    : activity.source;
}

/** The day a run started, such as "3 Oct 2026". */
export function runDate(activity?: ActivitySummary | null): string | null {
  if (!activity?.started_at) return null;
  return new Date(activity.started_at).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

// What the badge and the line both say about a run. A measurement's source is the
// acquisition system and its date is the shot's, neither of which tells a reader
// anything, so a measurement is given only its label.
function describe(type: ActivityType, activity: ActivitySummary) {
  const measured = type === 'measurement';
  return {
    ...ORIGIN[type],
    name: measured ? null : runName(activity),
    date: measured ? null : runDate(activity),
    fullName: measured ? null : [activity.source, activity.source_version].filter(Boolean).join(' '),
  };
}

/**
 * How a record came about: measured, analysed or simulated, by which code, and
 * when it ran.
 *
 * One shot can hold several datasets with the same name, such as a reconstructed
 * equilibrium and the equilibria of two simulation runs, and this is what tells
 * their cards apart. Two runs of the same code at the same version differ only in
 * when they ran, so the start date is shown as well.
 */
export function RunBadge({ activity }: { activity?: ActivitySummary | null }) {
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

/**
 * The run behind a record as one line of text, such as "Analysed by
 * fair-mast-ingestion ed6ea4e, 24 Sep 2026", linking to the run. For the top of
 * the record's own page, where a badge would be one more pill among the title's.
 * It takes its colour from `className`, so it reads on a light page or a dark band.
 */
export function RunLine({
  activity,
  activityId,
  className = '',
}: {
  activity?: ActivitySummary | null;
  activityId?: number | null;
  className?: string;
}) {
  if (!activity?.activity_type || activityId == null) return null;
  const { label, icon: Icon, name, date, fullName } = describe(activity.activity_type, activity);

  return (
    <p className={className}>
      <Link
        href={`/activities/${activityId}`}
        className="inline-flex items-center gap-1.5 hover:underline underline-offset-4"
        title={fullName || undefined}
      >
        <Icon className="w-4 h-4 shrink-0" aria-hidden />
        <span>
          {label}
          {name && <> by <span className="font-mono">{name}</span></>}
          {date && `, ${date}`}
        </span>
        <ChevronRight className="w-4 h-4 shrink-0" aria-hidden />
      </Link>
    </p>
  );
}
