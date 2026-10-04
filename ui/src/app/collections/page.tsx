'use client';

import { type ReactNode, useCallback, useEffect, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { fetcher, API_BASE } from '@/lib/api';
import { usePagedList } from '@/lib/use-paged-list';
import { LoadMore } from '@/components/load-more';
import { CollapsibleSection } from '@/components/collapsible-section';
import { Collection, Device } from '@/lib/types';
import { Layers, Database, ChevronRight, Globe, Server } from 'lucide-react';

const PAGE_SIZE = 100;
// A collection read inlines at most this many of each kind of member.
const INLINE_MEMBERS = 100;

function memberCount(count: number, noun: string): string {
  const shown = count >= INLINE_MEMBERS ? `${INLINE_MEMBERS}+` : `${count}`;
  return `${shown} ${noun}${count === 1 ? '' : 's'}`;
}

function CollectionCard({ col }: { col: Collection }) {
  return (
    <Link
      href={`/collections/${col.id}`}
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
        <span className="px-2.5 py-0.5 rounded-full border text-foreground bg-muted border-border">
          {col.effective_access_level || col.access_level}
        </span>
        {!!col.datasets?.length && (
          <span className="flex items-center gap-1">
            <Database className="w-3.5 h-3.5" />
            {memberCount(col.datasets.length, 'dataset')}
          </span>
        )}
        {!!col.child_collections?.length && (
          <span className="flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" />
            {memberCount(col.child_collections.length, 'collection')}
          </span>
        )}
      </div>
    </Link>
  );
}

// One scope's collections, read a page at a time as the list scrolls into view.
function ScopeCollections({
  scope,
  title,
  icon,
  url,
  onLoaded,
}: {
  scope: string;
  title: string;
  icon: ReactNode;
  url: string;
  onLoaded: (scope: string, count: number) => void;
}) {
  const { items, isLoading, done, loadingMore, loadMore } = usePagedList<Collection>(
    url,
    PAGE_SIZE
  );

  useEffect(() => {
    if (!isLoading) onLoaded(scope, items?.length ?? 0);
  }, [scope, isLoading, items?.length, onLoaded]);

  if (isLoading || !items?.length) return null;

  return (
    <CollapsibleSection
      label={
        <>
          {icon}
          <span className="text-base font-semibold">{title}</span>
          <span className="text-muted-foreground font-normal">
            ({done ? items.length : `${items.length}+`})
          </span>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {items.map((col) => (
          <CollectionCard key={col.id} col={col} />
        ))}
      </div>
      <LoadMore onLoad={loadMore} loading={loadingMore} done={done} />
    </CollapsibleSection>
  );
}

export default function CollectionsPage() {
  const { data: devices, isLoading } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const onLoaded = useCallback(
    (scope: string, count: number) =>
      setCounts((previous) =>
        previous[scope] === count ? previous : { ...previous, [scope]: count }
      ),
    []
  );

  const scopes = 1 + (devices?.length ?? 0);
  const settled = Object.keys(counts).length === scopes;
  const empty = !isLoading && settled && Object.values(counts).every((n) => n === 0);

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">Collections</h1>
        <p className="text-muted-foreground max-w-2xl">
          Collections group datasets into a single citable unit
          (<code className="text-foreground">dcat:Catalog</code>): the outputs of a run, a curated
          selection, or the contents of a store. Global collections are listed first, then each
          device&apos;s. A shot&apos;s own collections are listed on the shot.
        </p>
      </div>

      {isLoading && <div className="card p-8 text-center text-muted-foreground">Loading…</div>}

      {!isLoading && (
        <div className="space-y-3">
          <ScopeCollections
            scope="global"
            title="Global"
            icon={<Globe className="w-4 h-4 text-muted-foreground" />}
            url={`${API_BASE}/collections`}
            onLoaded={onLoaded}
          />
          {devices?.map((device) => (
            <ScopeCollections
              key={device.name}
              scope={device.name}
              title={device.title || device.name}
              icon={<Server className="w-4 h-4 text-muted-foreground" />}
              url={`${API_BASE}/devices/${device.name}/collections`}
              onLoaded={onLoaded}
            />
          ))}
        </div>
      )}

      {empty && (
        <div className="text-center py-16 bg-muted/30 rounded-lg border border-dashed border-border">
          <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
            <div className="bg-muted/50 p-4 rounded-full">
              <Layers className="w-12 h-12 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-2">No Collections Yet</h3>
              <p className="text-muted-foreground">
                Collections appear here once registered via the API.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
