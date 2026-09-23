'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { Activity, ArrowLeft, ChevronRight, Server, Globe, Link2 } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Source, SourceKind } from '@/lib/types';

// How each Source kind projects into the PROV-O graph. Instruments
// are entities (tools an activity uses), not agents.
const KIND_INFO: Record<SourceKind, { label: string; prov: string; isAgent: boolean }> = {
  software: { label: 'Software', prov: 'prov:SoftwareAgent', isAgent: true },
  instrument: { label: 'Instrument', prov: 'prov:Entity', isAgent: false },
  person: { label: 'Person', prov: 'prov:Person', isAgent: true },
  organization: { label: 'Organization', prov: 'prov:Organization', isAgent: true },
};

export default function SourceDetail({ id }: { id: string }) {
  const { data: source, error, isLoading } = useSWR<Source>(
    id ? `${API_BASE}/sources/id/${id}` : null,
    fetcher
  );

  const sourceName = source?.name ?? id;

  if (error) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link href="/sources" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sources
        </Link>
        <div className="card p-8 text-center text-destructive">
          Failed to load source &quot;{sourceName}&quot;
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-12 text-muted-foreground">
        Loading source details...
      </div>
    );
  }

  if (!source) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link href="/sources" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sources
        </Link>
        <div className="card p-8 text-center text-muted-foreground">
          Source &quot;{sourceName}&quot; not found.
        </div>
      </div>
    );
  }

  const isDeviceLinked = !!source.device_id;
  const kindInfo = source.kind ? KIND_INFO[source.kind] : null;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Navigation */}
      <div className="mb-8">
        <Link href="/sources" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sources
        </Link>
        <div className="flex items-center text-sm text-muted-foreground mb-2">
          <Link href="/sources" className="hover:text-primary transition-colors">Sources</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-foreground font-medium">{source.name}</span>
        </div>
      </div>

      {/* Source Header */}
      <div className="card overflow-hidden mb-8">
        <div className={`h-1.5 w-full ${
          isDeviceLinked
            ? 'bg-gradient-to-r from-muted to-muted'
            : 'bg-gradient-to-r from-muted to-muted'
        }`} />
        <div className="p-8">
          <div className="flex items-start gap-4 mb-6">
            <div className={`p-3 rounded-xl ${
              isDeviceLinked
                ? 'bg-muted text-foreground'
                : 'bg-muted text-foreground'
            }`}>
              <Activity className="w-8 h-8" />
            </div>
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-foreground mb-2">{source.name}</h1>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border font-medium ${
                  isDeviceLinked
                    ? 'text-foreground bg-muted border-border'
                    : 'text-foreground bg-muted border-border'
                }`}>
                  {isDeviceLinked ? (
                    <><Server className="w-3 h-3" /> Device-Linked Source</>
                  ) : (
                    <><Globe className="w-3 h-3" /> Global Source</>
                  )}
                </span>
                <span className="inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border font-medium text-foreground bg-muted border-border">
                  {kindInfo ? `${kindInfo.label} · ${kindInfo.prov}` : 'Unclassified'}
                </span>
              </div>
            </div>
          </div>

          {source.description ? (
            <p className="text-foreground text-lg leading-relaxed">{source.description}</p>
          ) : (
            <p className="text-muted-foreground italic">No description available for this source.</p>
          )}
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Metadata Card */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
            <Link2 className="w-5 h-5 text-muted-foreground" />
            Source Information
          </h2>
          <div className="space-y-4">
            <div>
              <dt className="text-sm text-muted-foreground mb-1">Name</dt>
              <dd className="text-foreground font-mono text-sm bg-card/50 px-3 py-2 rounded-lg">
                {source.name}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground mb-1">Kind</dt>
              <dd className="text-foreground text-sm">
                {kindInfo ? `${kindInfo.label} (${kindInfo.prov})` : 'Unclassified'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground mb-1">Scope</dt>
              <dd className="text-foreground text-sm">
                {isDeviceLinked ? `Device-Linked (ID: ${source.device_id})` : 'Global'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground mb-1">Internal ID</dt>
              <dd className="text-muted-foreground font-mono text-sm">{source.id}</dd>
            </div>
          </div>
        </div>

        {/* Provenance Info Card */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-muted-foreground" />
            Provenance
          </h2>
          <div className="space-y-3 text-sm text-muted-foreground">
            {kindInfo && !kindInfo.isAgent ? (
              <p className="leading-relaxed">
                This source is an <span className="text-foreground font-medium">instrument</span> — a tool, not an
                agent. In PROV-O it is a <span className="text-foreground font-medium">{kindInfo.prov}</span> that an{' '}
                <span className="text-foreground font-medium">Activity</span> <span className="font-mono text-xs">used</span>{' '}
                (role <span className="font-mono text-xs">instrument</span>), never the agent a run was associated with.
              </p>
            ) : (
              <p className="leading-relaxed">
                This source is a <span className="text-foreground font-medium">{kindInfo ? kindInfo.prov : 'prov:Agent'}</span>{' '}
                — it bears responsibility for the runs it performs. Each execution is recorded as an{' '}
                <span className="text-foreground font-medium">Activity</span> (prov:Activity) it{' '}
                <span className="font-mono text-xs">wasAssociatedWith</span>, linked to the datasets that run produced.
              </p>
            )}
            <p className="leading-relaxed">
              To trace what a run consumed and produced, open a dataset and check its Provenance panel, or
              request a dataset as{' '}
              <span className="font-mono text-foreground text-xs">application/ld+json</span>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
