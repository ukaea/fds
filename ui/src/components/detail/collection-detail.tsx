'use client';

import type { ReactNode } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { fetcher, API_BASE } from '@/lib/api';
import { Collection, Activity, Dataset } from '@/lib/types';
import { usePagedList } from '@/lib/use-paged-list';
import { LoadMore } from '@/components/load-more';
import ProvenanceGraph from '@/components/ProvenanceGraph';
import { ScientificMetadata } from '@/components/properties';
import { useDeviceLabel } from '@/lib/use-device-label';
import { Layers, Database, FileCode, ChevronRight, Activity as ActivityIcon } from 'lucide-react';
import { JsonLdPanel } from '@/components/jsonld-panel';
import { CollapsibleSection } from '@/components/collapsible-section';

function formatMediaType(mediaType?: string): string {
  if (!mediaType) return 'Zarr';
  if (mediaType.includes('zarr')) return 'Zarr';
  if (mediaType.includes('netcdf') || mediaType.includes('netCDF')) return 'NetCDF';
  if (mediaType.includes('hdf')) return 'HDF5';
  return mediaType.split('/').pop() || mediaType;
}

const PAGE_SIZE = 100;

function Property({ label, last, children }: { label: string; last?: boolean; children: ReactNode }) {
  return (
    <div className={`flex flex-col justify-start py-1 ${last ? '' : 'border-b border-border pb-2'}`}>
      <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">{label}</span>
      <span className="text-foreground">{children}</span>
    </div>
  );
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export default function CollectionDetail({ id }: { id: string }) {
  const { data: collection, error, isLoading } = useSWR<Collection>(
    id ? `${API_BASE}/collections/id/${id}` : null,
    fetcher
  );

  const deviceName = collection?.device_name ?? undefined;
  const deviceLabel = useDeviceLabel(deviceName);
  const shotId = collection?.shot_id ?? undefined;
  const collectionName = collection?.name;

  const children = usePagedList<Collection>(
    collection?.id != null ? `${API_BASE}/collections/${collection.id}/collections` : null,
    PAGE_SIZE
  );
  const members = usePagedList<Dataset>(
    collection?.id != null ? `${API_BASE}/collections/${collection.id}/datasets` : null,
    PAGE_SIZE
  );

  const { data: activity } = useSWR<Activity>(
    collection?.id != null && collection.activity_id != null
      ? `${API_BASE}/collections/${collection.id}/activity`
      : null,
    fetcher
  );

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 text-muted-foreground">Loading collection…</div>
    );
  }

  if (error || !collection) {
    return (
      <div className="container mx-auto px-4 py-8 text-destructive">
        Failed to load collection.
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center text-sm text-muted-foreground mb-6 flex-wrap gap-1">
        {deviceName && (
          <>
            <Link href={`/devices/${deviceName}`} className="hover:text-primary transition-colors">{deviceLabel}</Link>
            <ChevronRight className="w-4 h-4" />
          </>
        )}
        {deviceName && shotId && (
          <>
            <Link href={`/devices/${deviceName}/shots/${shotId}`} className="hover:text-primary transition-colors">Shot #{shotId}</Link>
          </>
        )}
        <ChevronRight className="w-4 h-4" />
        <span className="text-foreground font-medium">{collectionName}</span>
      </div>

      {/* Header */}
      <div className="flex items-start gap-4 mb-8">
        <div className="bg-muted p-3 rounded-xl text-foreground mt-1">
          <Layers className="w-7 h-7" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-foreground">{collection.title || collection.name}</h1>
          {collection.title && (
            <p className="text-muted-foreground font-mono text-sm mt-1">{collection.name}</p>
          )}
          {collection.description && (
            <p className="text-foreground mt-3 max-w-2xl">{collection.description}</p>
          )}
          <div className="flex items-center gap-3 mt-3">
            <span className="text-xs px-2.5 py-1 rounded-full border text-foreground bg-muted border-border">
              {collection.effective_access_level || collection.access_level}
            </span>
            <span className="text-xs text-muted-foreground">dcat:Catalog</span>
          </div>
        </div>
      </div>


      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-8">
          {!!children.items?.length && (
            <section>
              <div className="flex items-center gap-3 mb-4">
                <div className="bg-muted p-2 rounded-lg text-foreground">
                  <Layers className="w-5 h-5" />
                </div>
                <h2 className="text-lg font-semibold text-foreground">Member Collections</h2>
                {children.done && (
                  <span className="text-sm text-muted-foreground">({children.items.length})</span>
                )}
              </div>
              <div className="space-y-3">
                {children.items.map((child) => (
                  <Link
                    key={child.id}
                    href={`/collections/${child.id}`}
                    className="card p-4 hover:border-primary/50 transition-all group flex items-start justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div className="bg-muted p-2 rounded-sm text-foreground">
                        <Layers className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="font-semibold text-foreground group-hover:text-primary transition-colors">
                          {child.title || child.name}
                        </p>
                        {child.title && (
                          <p className="text-xs text-muted-foreground font-mono mt-0.5">{child.name}</p>
                        )}
                      </div>
                    </div>
                    <ChevronRight className="text-muted-foreground group-hover:text-primary transition-colors shrink-0 ml-4" />
                  </Link>
                ))}
              </div>
              <LoadMore onLoad={children.loadMore} loading={children.loadingMore} done={children.done} />
            </section>
          )}

          {(!!members.items?.length || !children.items?.length) && (
            <section>
              <div className="flex items-center gap-3 mb-4">
                <div className="bg-muted p-2 rounded-lg text-foreground">
                  <Database className="w-5 h-5" />
                </div>
                <h2 className="text-lg font-semibold text-foreground">Member Datasets</h2>
                {members.done && (
                  <span className="text-sm text-muted-foreground">({members.items?.length ?? 0})</span>
                )}
              </div>

              {members.items?.length ? (
                <div className="space-y-3">
                  {members.items.map((ds) => (
                    <Link
                      key={ds.id}
                      href={`/datasets/${ds.id}`}
                      className="card p-4 hover:border-primary/50 transition-all group flex items-start justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className="bg-muted p-2 rounded-sm text-foreground">
                          <Database className="w-4 h-4" />
                        </div>
                        <div>
                          <p className="font-semibold text-foreground group-hover:text-primary transition-colors">{ds.name}</p>
                          <p className="text-xs text-muted-foreground font-mono mt-0.5 truncate max-w-sm">{ds.url}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-4">
                        <span className="text-xs px-2 py-0.5 bg-muted rounded-sm text-foreground flex items-center gap-1">
                          <FileCode className="w-3 h-3" />
                          {formatMediaType(ds.media_type)}
                        </span>
                        <ChevronRight className="text-muted-foreground group-hover:text-primary transition-colors" />
                      </div>
                    </Link>
                  ))}
                  <LoadMore onLoad={members.loadMore} loading={members.loadingMore} done={members.done} />
                </div>
              ) : members.isLoading || children.isLoading ? (
                <div className="card p-8 text-center text-muted-foreground">Loading members…</div>
              ) : (
                <div className="card p-8 text-center text-muted-foreground">No datasets in this collection.</div>
              )}
            </section>
          )}
        </div>

        <div className="space-y-6">
          <div className="card p-6 bg-card/60 shadow-xl border-border">
            <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground">Collection Properties</h3>
            <div className="space-y-3 text-sm">
              <Property label="Created At">
                {collection.created_at
                  ? new Date(collection.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
                  : 'Unknown'}
              </Property>
              <Property label="Scope">
                {shotId ? `${deviceLabel} / Shot ${shotId}` : deviceName ? deviceLabel : 'Global'}
              </Property>
              {collection.root_url && (
                <Property label="Root URL">
                  <span className="font-mono break-all">{collection.root_url}</span>
                </Property>
              )}
              <Property label="Access Level" last>
                <span className="capitalize">{collection.effective_access_level || collection.access_level || 'Unknown'}</span>
              </Property>
            </div>
          </div>

          <ScientificMetadata properties={collection.scientific_metadata} className="bg-card/60 shadow-xl border-border" />

          <div className="card p-6 bg-card/60 shadow-xl border-border">
            <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
              <ActivityIcon className="w-5 h-5 text-muted-foreground" /> Provenance
            </h3>
            {activity ? (
              <div className="space-y-3 text-sm">
                {activity.activity_type && <Property label="Activity Type">{activity.activity_type}</Property>}
                {activity.source_version && (
                  <Property label="Source Version">
                    <span className="font-mono">{activity.source_version}</span>
                  </Property>
                )}
                {activity.started_at && <Property label="Started">{formatDate(activity.started_at)}</Property>}
                {activity.ended_at && <Property label="Ended">{formatDate(activity.ended_at)}</Property>}
                {activity.parameters && Object.keys(activity.parameters).length > 0 && (
                  <Property label="Parameters" last>
                    <pre className="text-xs font-mono bg-background border border-border p-2 rounded-sm overflow-x-auto">
                      {JSON.stringify(activity.parameters, null, 2)}
                    </pre>
                  </Property>
                )}
              </div>
            ) : collection.activity_id ? (
              <p className="text-muted-foreground text-sm">Loading provenance…</p>
            ) : (
              <div className="text-center py-4 bg-card/30 rounded-lg border border-dashed border-border">
                <p className="text-xs text-muted-foreground">No activity is recorded for this collection.</p>
              </div>
            )}
            <CollapsibleSection
              label="Provenance graph"
              className="mt-4 -mx-4 border-t border-border"
            >
              <ProvenanceGraph collection={collection} />
            </CollapsibleSection>
          </div>

          <JsonLdPanel url={`${API_BASE}/collections/id/${id}`} />
        </div>
      </div>
    </div>
  );
}
