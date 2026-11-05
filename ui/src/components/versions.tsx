'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { History } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { ActivitySummary } from '@/lib/types';
import { ActivityBadge } from '@/components/activity-label';

// The record kinds whose versions a page can list, as they appear in API and
// page paths.
export type VersionKind = 'datasets';

const NOUN: Record<VersionKind, string> = { datasets: 'Dataset' };
const LINK = 'text-primary underline underline-offset-4 hover:text-foreground';

// What a version's link says about it, read from the record itself.
interface VersionSummary {
  name: string;
  activity?: ActivitySummary | null;
  created_at?: string;
}

// Another version: its name as a link, and the Activity that generated it, which
// is what tells versions of the same name apart. A version with no Activity is
// told apart by when it was listed instead. A record this one replaces may be
// one the reader cannot read; its link then shows only its id, and the fetch is
// not retried.
function VersionLink({ kind, id }: { kind: VersionKind; id: number }) {
  const { data } = useSWR<VersionSummary>(`${API_BASE}/${kind}/id/${id}`, fetcher, {
    shouldRetryOnError: false,
  });
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Link href={`/${kind}/${id}`} className={`font-medium ${LINK}`}>{data?.name ?? `${NOUN[kind]} ${id}`}</Link>
      {data?.activity ? (
        <ActivityBadge activity={data.activity} />
      ) : data?.created_at && (
        <span className="text-xs text-muted-foreground">
          listed {new Date(data.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
        </span>
      )}
    </span>
  );
}

/** Other versions of a record, such as those it replaces, one per line. */
export function VersionList({ kind, ids }: { kind: VersionKind; ids: number[] }) {
  return (
    <ul className="space-y-2">
      {ids.map((id) => <li key={id}><VersionLink kind={kind} id={id} /></li>)}
    </ul>
  );
}

/**
 * That a newer version replaces this record, or nothing when none does. The
 * text stays in the foreground colour: the orange is below AA contrast on a
 * card's background.
 */
export function ReplacedNotice({ kind, replacedBy }: { kind: VersionKind; replacedBy: number[] }) {
  if (replacedBy.length === 0) return null;
  return (
    <div className="mb-4 flex items-start gap-2 rounded-sm border border-border border-l-4 border-l-brand bg-card p-3 text-sm text-foreground">
      <History className="w-4 h-4 shrink-0 mt-0.5 text-brand" aria-hidden />
      <p>
        {replacedBy.length === 1 ? 'A newer version replaces this one: ' : 'Newer versions replace this one: '}
        {replacedBy.map((id, i) => (
          <span key={id}>{i > 0 && ', '}<VersionLink kind={kind} id={id} /></span>
        ))}
      </p>
    </div>
  );
}
