'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { fetcher, API_BASE } from '@/lib/api';
import { Source, Collection } from '@/lib/types';
import { Layers, Database, ChevronRight, Activity, Server } from 'lucide-react';

function formatScope(col: Collection): string {
  if (col.device_name && col.shot_id) return `${col.device_name} / Shot ${col.shot_id}`;
  if (col.device_name) return col.device_name;
  return 'Global';
}

function collectionHref(col: Collection): string {
  if (col.device_name && col.shot_id) {
    return `/devices/${col.device_name}/shots/${col.shot_id}/collections/${col.name}`;
  }
  if (col.device_name) {
    return `/devices/${col.device_name}/collections/${col.name}`;
  }
  return `/collections/${col.name}`;
}

// Fetches and renders collections for a single source
function SourceCollections({ source }: { source: Source }) {
  const { data: collections, isLoading } = useSWR<Collection[]>(
    `${API_BASE}/sources/${source.name}/collections`,
    fetcher
  );

  if (isLoading || !collections || collections.length === 0) return null;

  return (
    <div className="mb-10">
      <div className="flex items-center gap-3 mb-4">
        <div className="bg-muted p-2 rounded-lg text-foreground">
          <Activity className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground">{source.name}</h2>
          {source.description && (
            <p className="text-sm text-muted-foreground">{source.description}</p>
          )}
        </div>
        <span className="text-sm text-muted-foreground ml-1">({collections.length})</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {collections.map((col) => (
          <Link
            key={col.id}
            href={collectionHref(col)}
            className="card p-5 hover:border-border transition-all group"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="bg-muted p-2 rounded-lg text-foreground">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground group-hover:text-foreground transition-colors">
                    {col.title || col.name}
                  </h3>
                  {col.title && (
                    <p className="text-xs text-muted-foreground font-mono mt-0.5">{col.name}</p>
                  )}
                  {col.description && (
                    <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{col.description}</p>
                  )}
                </div>
              </div>
              <ChevronRight className="text-muted-foreground group-hover:text-foreground opacity-0 group-hover:opacity-100 transition-all shrink-0 ml-4" />
            </div>

            <div className="mt-4 flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Server className="w-3.5 h-3.5" />
                {formatScope(col)}
              </span>
              <span className="px-2.5 py-0.5 rounded-full border text-foreground bg-muted border-border">
                {col.effective_access_level || col.access_level}
              </span>
              {col.datasets && (
                <span className="flex items-center gap-1">
                  <Database className="w-3.5 h-3.5" />
                  {col.datasets.length} dataset{col.datasets.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function CollectionsPage() {
  const { data: sources, isLoading } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);

  const hasAnySources = sources && sources.length > 0;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">Collections</h1>
        <p className="text-muted-foreground max-w-2xl">
          Collections group the outputs of a simulation or analysis run into a single citable unit
          (<code className="text-foreground">dcat:Catalog</code>). They are organised here by the
          source code that produced them.
        </p>
      </div>

      {isLoading && (
        <div className="card p-8 text-center text-muted-foreground">Loading…</div>
      )}

      {!isLoading && hasAnySources && (
        <div>
          {sources.map((source) => (
            <SourceCollections key={source.id} source={source} />
          ))}
        </div>
      )}

      {!isLoading && !hasAnySources && (
        <div className="text-center py-16 bg-muted/30 rounded-lg border border-dashed border-border">
          <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
            <div className="bg-muted/50 p-4 rounded-full">
              <Layers className="w-12 h-12 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-2">No Collections Yet</h3>
              <p className="text-muted-foreground">
                Collections appear here once registered via the API or the demonstration notebook.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
