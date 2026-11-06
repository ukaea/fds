'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { Database, ExternalLink, FileCode } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import {
  ActivitySummary,
  ActivityType,
  FederatedSearch,
  FederationMember,
  MemberAnswer,
  MemberDataset,
} from '@/lib/types';
import { ActivityBadge } from '@/components/activity-label';
import { BADGE, formatMediaType } from '@/components/dataset-card';

const NOTE = 'card p-4 text-sm text-muted-foreground';
const ACTIVITY_TYPES: ActivityType[] = ['measurement', 'simulation', 'analysis', 'calibration'];

// Each change to a search goes over the network to every member, so typing in
// a filter waits for a pause before the members are asked.
const PAUSE_MS = 500;

type Node = Record<string, unknown>;

/** A JSON-LD value as text: a string, a number, or the first of a list. */
function text(value: unknown): string | undefined {
  if (Array.isArray(value)) return text(value[0]);
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (value && typeof value === 'object' && '@value' in value) {
    return text((value as Node)['@value']);
  }
  return undefined;
}

/** A JSON-LD value as the nodes it holds: one node, or each node of a list. */
function nodes(value: unknown): Node[] {
  const values = Array.isArray(value) ? value : [value];
  return values.filter((v): v is Node => !!v && typeof v === 'object');
}

/**
 * The Activity that generated a member's dataset, in the shape the Activity
 * badge takes: its type, the code that carried it out, the code's version and
 * when it started. A type outside FDS's own is left out.
 */
function activitySummary(dataset: MemberDataset): ActivitySummary | null {
  const [activity] = nodes(dataset['prov:wasGeneratedBy']);
  if (!activity) return null;
  const associations = nodes(activity['prov:qualifiedAssociation']);
  const executor =
    associations.find((a) => text(nodes(a['prov:hadRole'])[0]?.['@id']) === 'fuel:executor') ??
    associations[0];
  const agentId = text(nodes(executor?.['prov:agent'])[0]?.['@id']);
  const agents = nodes(activity['prov:wasAssociatedWith']);
  const agent = agents.find((a) => a['@id'] === agentId) ?? agents[0];
  const type = text(activity['prov:type']);
  return {
    activity_type: ACTIVITY_TYPES.find((t) => t === type) ?? null,
    source: text(agent?.title) ?? null,
    source_version: text(nodes(executor?.['prov:hadPlan'])[0]?.version) ?? null,
    started_at: text(activity['prov:startedAtTime']) ?? null,
  };
}

/**
 * A dataset another catalogue holds, laid out as a dataset card is. It opens the
 * dataset's page in that catalogue, which is where the record is kept.
 */
export function MemberDatasetCard({
  dataset,
  member,
  showContext = false,
}: {
  dataset: MemberDataset;
  member: FederationMember;
  showContext?: boolean;
}) {
  const device = text(dataset['fuel:device']);
  const shot = text(dataset['fuel:shot']);
  const [distribution] = nodes(dataset['dcat:distribution']);

  return (
    <a
      href={dataset['@id']}
      target="_blank"
      rel="noopener noreferrer"
      className="card p-6 block hover:border-primary/50 transition-colors"
    >
      <div className="flex items-start gap-3">
        <div className="bg-muted p-2 rounded-sm text-foreground">
          <Database className="w-5 h-5" />
        </div>
        <h3 className="font-bold text-lg text-foreground min-w-0 flex-1 [overflow-wrap:anywhere]">
          {text(dataset.title) ?? dataset['@id']}
        </h3>
        <ExternalLink className="w-4 h-4 text-muted-foreground shrink-0" />
      </div>

      <div className="mt-4 flex items-center gap-3 text-sm text-muted-foreground flex-wrap">
        <div className="flex items-center gap-1">
          <FileCode className="w-4 h-4" />
          {formatMediaType(text(distribution?.mediaType))}
        </div>
        <ActivityBadge activity={activitySummary(dataset)} />
        {showContext && device && <span className={BADGE}>{device}</span>}
        {showContext && <span className={BADGE}>{shot ? `shot ${shot}` : 'device level'}</span>}
        <span className={BADGE}>from {member.title}</span>
      </div>
    </a>
  );
}

/** The catalogues this FDS asks when someone searches across catalogues. */
export function useFederationMembers(): FederationMember[] | undefined {
  const { data } = useSWR<FederationMember[]>(`${API_BASE}/federation/members`, fetcher);
  return data;
}

function useAfterPause<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

function Answer({
  answer,
  limit,
  showContext,
}: {
  answer: MemberAnswer;
  limit: number;
  showContext: boolean;
}) {
  const { member, status, detail, datasets } = answer;
  if (status === 'failed') {
    return <div className={NOTE}>{member.title} did not answer: {detail}.</div>;
  }
  if (datasets.length === 0) {
    return <div className={NOTE}>{member.title} has no datasets that match.</div>;
  }
  return (
    <div>
      <p className="text-sm text-muted-foreground mb-3">
        {member.title}: {datasets.length === limit ? `the first ${limit}` : datasets.length}{' '}
        dataset{datasets.length === 1 ? '' : 's'}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datasets.map((dataset) => (
          <MemberDatasetCard
            key={dataset['@id']}
            dataset={dataset}
            member={member}
            showContext={showContext}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * What each member catalogue answers to one federated dataset listing, member by
 * member. FDS keeps none of it: the members are asked when `url` changes, after a
 * pause, and each card links to the dataset in its own catalogue.
 *
 * `url` is a listing under `/federation` with at most `limit` datasets from each
 * member.
 */
export function MemberAnswers({
  members,
  url,
  limit,
  showContext = false,
}: {
  members: FederationMember[];
  url: string;
  limit: number;
  showContext?: boolean;
}) {
  const settled = useAfterPause(url, PAUSE_MS);
  const { data, error, isLoading } = useSWR<FederatedSearch>(settled, fetcher);
  const names = members.map((member) => member.title).join(', ');

  if (error) {
    return <div className="card p-4 text-sm text-destructive">Failed to ask other catalogues.</div>;
  }
  if (isLoading || settled !== url || !data) {
    return <div className={NOTE}>Asking {names}…</div>;
  }
  return (
    <div className="space-y-6">
      {data.answers.map((answer) => (
        <Answer key={answer.member.id} answer={answer} limit={limit} showContext={showContext} />
      ))}
    </div>
  );
}
