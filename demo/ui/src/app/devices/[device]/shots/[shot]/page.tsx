'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, Collection } from '@/lib/types';
import { Database, FileCode, ChevronRight, Layers } from 'lucide-react';

function formatMediaType(mediaType?: string): string {
  if (!mediaType) return 'Zarr';
  if (mediaType.includes('zarr')) return 'Zarr';
  if (mediaType.includes('netcdf') || mediaType.includes('netCDF')) return 'NetCDF';
  if (mediaType.includes('hdf')) return 'HDF5';
  return mediaType.split('/').pop() || mediaType;
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

      {/* Collections */}
      {collections && collections.length > 0 && (
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-amber-500/20 p-2 rounded-lg text-amber-400">
              <Layers className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-white">Collections</h2>
            <span className="text-sm text-slate-500">({collections.length})</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {collections.map((col) => (
              <Link
                key={col.name}
                href={`/devices/${deviceName}/shots/${shotId}/collections/${col.name}`}
                className="card p-6 hover:border-amber-500/50 transition-all group"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="bg-amber-500/20 p-2 rounded text-amber-400">
                      <Layers className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="font-bold text-lg group-hover:text-amber-400 transition-colors">{col.name}</h3>
                      {col.title && <p className="text-sm text-slate-400 mt-0.5">{col.title}</p>}
                    </div>
                  </div>
                  <ChevronRight className="text-slate-600 group-hover:text-amber-400 opacity-0 group-hover:opacity-100 transition-all" />
                </div>
                <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
                  <span className="text-xs px-2.5 py-1 rounded-full border text-amber-400 bg-amber-500/10 border-amber-500/20">
                    {col.effective_access_level || col.access_level}
                  </span>
                  {col.datasets && (
                    <span>{col.datasets.length} dataset{col.datasets.length !== 1 ? 's' : ''}</span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Datasets */}
      <div className="flex items-center gap-3 mb-4">
        <div className="bg-purple-500/20 p-2 rounded-lg text-purple-400">
          <Database className="w-5 h-5" />
        </div>
        <h2 className="text-xl font-semibold text-white">Datasets</h2>
        {datasets && <span className="text-sm text-slate-500">({datasets.length})</span>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datasets?.map((dataset) => (
          <Link
            key={dataset.name}
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
        ))}

        {!datasets && !isLoading && !error && (
          <div className="col-span-full py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-lg">
            No datasets found for this shot.
          </div>
        )}
      </div>
    </div>
  );
}
