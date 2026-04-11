'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Collection, Activity } from '@/lib/types';
import { Layers, Database, FileCode, ChevronRight, Activity as ActivityIcon, Clock, ExternalLink } from 'lucide-react';

function formatMediaType(mediaType?: string): string {
  if (!mediaType) return 'Zarr';
  if (mediaType.includes('zarr')) return 'Zarr';
  if (mediaType.includes('netcdf') || mediaType.includes('netCDF')) return 'NetCDF';
  if (mediaType.includes('hdf')) return 'HDF5';
  return mediaType.split('/').pop() || mediaType;
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export default function CollectionDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const shotId = params.shot as string;
  const collectionName = params.collection as string;

  const { data: collection, error, isLoading } = useSWR<Collection>(
    deviceName && shotId && collectionName
      ? `${API_BASE}/devices/${deviceName}/shots/${shotId}/collections/${collectionName}`
      : null,
    fetcher
  );

  const { data: activity } = useSWR<Activity>(
    collection?.id != null && collection.activity_id != null
      ? `${API_BASE}/collections/${collection.id}/activity`
      : null,
    fetcher
  );

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 text-slate-400">Loading collection…</div>
    );
  }

  if (error || !collection) {
    return (
      <div className="container mx-auto px-4 py-8 text-red-400">
        Failed to load collection.
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center text-sm text-slate-400 mb-6 flex-wrap gap-1">
        <Link href={`/devices/${deviceName}`} className="hover:text-primary transition-colors">{deviceName}</Link>
        <ChevronRight className="w-4 h-4" />
        <Link href={`/devices/${deviceName}/shots/${shotId}`} className="hover:text-primary transition-colors">Shot #{shotId}</Link>
        <ChevronRight className="w-4 h-4" />
        <span className="text-white font-medium">{collectionName}</span>
      </div>

      {/* Header */}
      <div className="flex items-start gap-4 mb-8">
        <div className="bg-amber-500/20 p-3 rounded-xl text-amber-400 mt-1">
          <Layers className="w-7 h-7" />
        </div>
        <div>
          <h1 className="text-3xl font-bold text-white">{collection.title || collection.name}</h1>
          {collection.title && (
            <p className="text-slate-400 font-mono text-sm mt-1">{collection.name}</p>
          )}
          {collection.description && (
            <p className="text-slate-300 mt-3 max-w-2xl">{collection.description}</p>
          )}
          <div className="flex items-center gap-3 mt-3">
            <span className="text-xs px-2.5 py-1 rounded-full border text-amber-400 bg-amber-500/10 border-amber-500/20">
              {collection.effective_access_level || collection.access_level}
            </span>
            <span className="text-xs text-slate-500">dcat:Catalog</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Member datasets */}
        <div className="lg:col-span-2">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-purple-500/20 p-2 rounded-lg text-purple-400">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-lg font-semibold text-white">Member Datasets</h2>
            <span className="text-sm text-slate-500">({collection.datasets?.length ?? 0})</span>
          </div>

          {collection.datasets && collection.datasets.length > 0 ? (
            <div className="space-y-3">
              {collection.datasets.map((ds) => (
                <Link
                  key={ds.name}
                  href={`/devices/${deviceName}/shots/${shotId}/datasets/${ds.id}`}
                  className="card p-4 hover:border-primary/50 transition-all group flex items-start justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className="bg-purple-500/20 p-2 rounded text-purple-400">
                      <Database className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="font-semibold text-white group-hover:text-primary transition-colors">{ds.name}</p>
                      <p className="text-xs text-slate-500 font-mono mt-0.5 truncate max-w-sm">{ds.url}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    <span className="text-xs px-2 py-0.5 bg-slate-700 rounded text-slate-300 flex items-center gap-1">
                      <FileCode className="w-3 h-3" />
                      {formatMediaType(ds.media_type)}
                    </span>
                    <ChevronRight className="text-slate-600 group-hover:text-primary transition-colors" />
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="card p-8 text-center text-slate-500">No datasets in this collection.</div>
          )}
        </div>

        {/* Provenance sidebar */}
        <div className="space-y-4">
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <ActivityIcon className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-semibold text-white">Provenance</h3>
            </div>

            {activity ? (
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-slate-500 text-xs mb-1">Activity type</p>
                  <p className="text-slate-200 font-mono">{activity.activity_type || '—'}</p>
                </div>
                {activity.source_version && (
                  <div>
                    <p className="text-slate-500 text-xs mb-1">Source version</p>
                    <p className="text-slate-200 font-mono">{activity.source_version}</p>
                  </div>
                )}
                {activity.started_at && (
                  <div>
                    <p className="text-slate-500 text-xs mb-1">Started</p>
                    <p className="text-slate-200 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      {formatDate(activity.started_at)}
                    </p>
                  </div>
                )}
                {activity.ended_at && (
                  <div>
                    <p className="text-slate-500 text-xs mb-1">Ended</p>
                    <p className="text-slate-200 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      {formatDate(activity.ended_at)}
                    </p>
                  </div>
                )}
                {activity.parameters && Object.keys(activity.parameters).length > 0 && (
                  <div>
                    <p className="text-slate-500 text-xs mb-1">Parameters</p>
                    <pre className="text-xs text-slate-300 bg-slate-900/50 rounded p-2 overflow-x-auto">
                      {JSON.stringify(activity.parameters, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ) : collection.activity_id ? (
              <p className="text-slate-500 text-sm">Loading provenance…</p>
            ) : (
              <p className="text-slate-500 text-sm">No provenance recorded.</p>
            )}
          </div>

          {/* JSON-LD link */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <ExternalLink className="w-4 h-4 text-slate-400" />
              <h3 className="text-sm font-semibold text-white">Semantic Metadata</h3>
            </div>
            <p className="text-xs text-slate-400 mb-3">
              This collection is serialisable as a <code className="text-slate-300">dcat:Catalog</code> with full PROV-O provenance.
            </p>
            <a
              href={`/api/v1/devices/${deviceName}/shots/${shotId}/collections/${collectionName}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
              onClick={(e) => {
                // Modify Accept header isn't possible via plain <a>, so just link to the endpoint
                e.preventDefault();
                window.open(
                  `/api/v1/devices/${deviceName}/shots/${shotId}/collections/${collectionName}`,
                  '_blank'
                );
              }}
            >
              View raw JSON <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
