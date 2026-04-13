'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, Collection, Activity, Source } from '@/lib/types';
import { Database, FileCode, ChevronRight, Layers } from 'lucide-react';

function formatMediaType(mediaType?: string): string {
  if (!mediaType) return 'Zarr';
  if (mediaType.includes('zarr')) return 'Zarr';
  if (mediaType.includes('netcdf') || mediaType.includes('netCDF')) return 'NetCDF';
  if (mediaType.includes('hdf')) return 'HDF5';
  return mediaType.split('/').pop() || mediaType;
}

function formatSourceName(name: string): string {
  return name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatDate(iso?: string): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function DatasetCard({ dataset, deviceName, shotId }: { dataset: Dataset; deviceName: string; shotId: string }) {
  return (
    <Link
      href={`/devices/${deviceName}/shots/${shotId}/datasets/${dataset.id}`}
      className="card p-6 hover:border-primary/50 transition-all group"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-purple-500/20 p-2 rounded text-purple-400">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-lg group-hover:text-primary transition-colors">{dataset.name}</h3>
            <p className="text-xs text-slate-500 font-mono mt-1 truncate max-w-xs">{dataset.url}</p>
          </div>
        </div>
        <ChevronRight className="text-slate-600 group-hover:text-primary opacity-0 group-hover:opacity-100 transition-all" />
      </div>

      <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
        <div className="flex items-center gap-1">
          <FileCode className="w-4 h-4" />
          {formatMediaType(dataset.media_type)}
        </div>
        {dataset.level !== undefined && (
          <span className="text-xs px-2 py-0.5 bg-blue-500/10 border border-blue-500/20 text-blue-400 rounded-full">
            L{dataset.level}
          </span>
        )}
        <span className="text-emerald-400 text-xs px-2 py-0.5 bg-emerald-500/10 rounded-full border border-emerald-500/20">
          {dataset.effective_access_level || dataset.access_level || 'public'}
        </span>
      </div>
    </Link>
  );
}

function CollectionSection({
  collection,
  sourcesById,
  deviceName,
  shotId,
}: {
  collection: Collection;
  sourcesById: Map<number, string>;
  deviceName: string;
  shotId: string;
}) {
  const { data: activity } = useSWR<Activity>(
    collection.activity_id ? `${API_BASE}/activities/${collection.activity_id}` : null,
    fetcher
  );

  const sourceName = activity?.source_id != null ? sourcesById.get(activity.source_id) : undefined;
  let activityLabel: string | undefined;
  if (sourceName) {
    activityLabel = formatSourceName(sourceName);
    if (activity?.started_at) activityLabel += ` · ${formatDate(activity.started_at)}`;
  } else if (activity?.activity_type) {
    activityLabel = activity.activity_type;
    if (activity.started_at) activityLabel += ` · ${formatDate(activity.started_at)}`;
  }

  const datasetCount = collection.datasets?.length ?? 0;

  return (
    <div className="mb-10">
      <div className="flex items-center gap-3 mb-4">
        <div className="bg-amber-500/20 p-2 rounded-lg text-amber-400">
          <Layers className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-white">{collection.title || collection.name}</h2>
          {activityLabel && (
            <p className="text-sm text-slate-400 mt-0.5">{activityLabel}</p>
          )}
        </div>
        <span className="text-sm text-slate-500 ml-1">
          ({datasetCount} dataset{datasetCount !== 1 ? 's' : ''})
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {collection.datasets?.map((dataset) => (
          <DatasetCard key={dataset.id ?? dataset.name} dataset={dataset} deviceName={deviceName} shotId={shotId} />
        ))}
      </div>
    </div>
  );
}

export default function ShotDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const shotId = params.shot as string;

  const { data: datasets, error, isLoading } = useSWR<Dataset[]>(
    deviceName && shotId ? `${API_BASE}/devices/${deviceName}/shots/${shotId}/datasets` : null,
    fetcher
  );

  const { data: collections } = useSWR<Collection[]>(
    deviceName && shotId ? `${API_BASE}/devices/${deviceName}/shots/${shotId}/collections` : null,
    fetcher
  );

  const { data: sources } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);

  const sourcesById = new Map<number, string>(sources?.map(s => [s.id, s.name]) ?? []);

  // Datasets already shown inside a collection
  const datasetIdsInCollections = new Set<number>(
    collections?.flatMap(col => col.datasets?.map(ds => ds.id).filter((id): id is number => id != null) ?? []) ?? []
  );
  const uncollectedDatasets = datasets?.filter(ds => ds.id != null && !datasetIdsInCollections.has(ds.id!)) ?? [];

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center text-sm text-slate-400 mb-2">
          <Link href={`/devices/${deviceName}`} className="hover:text-primary transition-colors">{deviceName}</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-white font-medium">Shot #{shotId}</span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Shot #{shotId}</h1>
        <p className="text-slate-400">Scientific data and collections for this shot.</p>
      </div>

      {isLoading && (
        <div className="card p-6 text-center text-slate-400">Loading datasets…</div>
      )}
      {error && (
        <div className="card p-6 text-center text-red-400">Failed to load datasets.</div>
      )}

      {/* One section per collection */}
      {collections?.map((collection) => (
        <CollectionSection
          key={collection.id}
          collection={collection}
          sourcesById={sourcesById}
          deviceName={deviceName}
          shotId={shotId}
        />
      ))}

      {/* Datasets not in any collection */}
      {uncollectedDatasets.length > 0 && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-purple-500/20 p-2 rounded-lg text-purple-400">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-white">Other Datasets</h2>
            <span className="text-sm text-slate-500">({uncollectedDatasets.length})</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {uncollectedDatasets.map((dataset) => (
              <DatasetCard key={dataset.id ?? dataset.name} dataset={dataset} deviceName={deviceName} shotId={shotId} />
            ))}
          </div>
        </div>
      )}

      {!isLoading && !error && datasets?.length === 0 && (
        <div className="py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-lg">
          No datasets found for this shot.
        </div>
      )}
    </div>
  );
}
