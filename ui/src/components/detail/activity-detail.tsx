'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { Activity as ActivityIcon, ArrowLeft, ChevronRight, Clock, Cpu, Database, Settings } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Activity, Dataset, Source } from '@/lib/types';

function formatTime(value?: string): string {
  if (!value) return 'not recorded';
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export default function ActivityDetail({ id }: { id: string }) {
  const { data: activity, error, isLoading } = useSWR<Activity>(
    id ? `${API_BASE}/activities/${id}` : null,
    fetcher
  );

  const { data: executor } = useSWR<Source>(
    activity?.source_id != null ? `${API_BASE}/sources/id/${activity.source_id}` : null,
    fetcher
  );

  const { data: inputs } = useSWR<Dataset[]>(
    id ? `${API_BASE}/activities/${id}/inputs` : null,
    fetcher
  );

  const { data: instruments } = useSWR<Source[]>(
    id ? `${API_BASE}/activities/${id}/instruments` : null,
    fetcher
  );

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-12 text-muted-foreground">
        Loading activity details...
      </div>
    );
  }

  if (error || !activity) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link href="/datasets" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Datasets
        </Link>
        <div className="card p-8 text-center text-muted-foreground">
          Activity {id} not found.
        </div>
      </div>
    );
  }

  const parameters = activity.parameters ?? {};
  const parameterNames = Object.keys(parameters);

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center text-sm text-muted-foreground mb-2">
          <Link href="/datasets" className="hover:text-primary transition-colors">Datasets</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-foreground font-medium">Activity {activity.id}</span>
        </div>
      </div>

      <div className="card overflow-hidden mb-8">
        <div className="h-1.5 w-full bg-gradient-to-r from-muted to-muted" />
        <div className="p-8">
          <div className="flex items-start gap-4 mb-6">
            <div className="p-3 rounded-xl bg-muted text-foreground">
              <ActivityIcon className="w-8 h-8" />
            </div>
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-foreground mb-2">
                {activity.activity_type || `Activity ${activity.id}`}
              </h1>
              <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border font-medium text-foreground bg-muted border-border">
                prov:Activity
              </span>
            </div>
          </div>

          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground mb-1 flex items-center gap-1.5">
                <Clock className="w-3 h-3" /> Started
              </dt>
              <dd className="text-sm text-foreground">{formatTime(activity.started_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground mb-1 flex items-center gap-1.5">
                <Clock className="w-3 h-3" /> Ended
              </dt>
              <dd className="text-sm text-foreground">{formatTime(activity.ended_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground mb-1 flex items-center gap-1.5">
                <Cpu className="w-3 h-3" /> Carried out by
              </dt>
              <dd className="text-sm text-foreground">
                {activity.source_id == null ? (
                  <span className="text-muted-foreground">no agent recorded</span>
                ) : (
                  <Link href={`/sources/${activity.source_id}`} className="hover:text-primary transition-colors">
                    {executor?.name ?? `Source ${activity.source_id}`}
                  </Link>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Version</dt>
              <dd className="text-sm text-foreground font-mono">
                {activity.source_version || <span className="font-sans text-muted-foreground">not recorded</span>}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {parameterNames.length > 0 && (
        <div className="card p-6 mb-8">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Settings className="w-4 h-4" /> Parameters
          </h2>
          <dl className="grid gap-2 sm:grid-cols-2">
            {parameterNames.map((name) => (
              <div key={name} className="flex gap-2 text-sm">
                <dt className="text-muted-foreground font-mono">{name}</dt>
                <dd className="text-foreground font-mono break-all">{JSON.stringify(parameters[name])}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {(instruments?.length ?? 0) > 0 && (
        <div className="card p-6 mb-8">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Cpu className="w-4 h-4" /> Instruments used
          </h2>
          <ul className="space-y-2">
            {instruments?.map((instrument) => (
              <li key={instrument.id}>
                <Link href={`/sources/${instrument.id}`} className="text-sm text-foreground hover:text-primary transition-colors">
                  {instrument.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(inputs?.length ?? 0) > 0 && (
        <div className="card p-6">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Database className="w-4 h-4" /> Datasets it used
          </h2>
          <ul className="space-y-2">
            {inputs?.map((dataset) => (
              <li key={dataset.id}>
                <Link href={`/datasets/${dataset.id}`} className="text-sm text-foreground hover:text-primary transition-colors">
                  {dataset.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
