'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset } from '@/lib/types';
import { Database, FileCode, ChevronRight, ArrowLeft } from 'lucide-react';

export default function ShotDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const shotId = params.shot as string; // Note: Next.js params are strings

  const { data: datasets, error, isLoading } = useSWR<Dataset[]>(
    deviceName && shotId ? `${API_BASE}/devices/${deviceName}/shots/${shotId}/datasets` : null,
    fetcher
  );

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
         <Link href={`/devices/${deviceName}/shots`} className="inline-flex items-center text-sm text-slate-400 hover:text-white mb-4 transition-colors">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Shot List
         </Link>
        <div className="flex items-center text-sm text-slate-400 mb-2">
            <span className="text-slate-500">{deviceName}</span>
            <ChevronRight className="w-4 h-4 mx-2" />
            <span className="text-white font-medium">Shot #{shotId}</span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Datasets</h1>
        <p className="text-slate-400">Available scientific data for Shot #{shotId}.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datasets?.map((dataset) => (
          <Link
            key={dataset.name}
            href={`/devices/${deviceName}/shots/${shotId}/datasets/${dataset.name}`}
            className="card p-6 hover:border-primary/50 transition-all group"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                 <div className="bg-purple-500/20 p-2 rounded text-purple-400">
                    <Database className="w-5 h-5" />
                 </div>
                 <div>
                    <h3 className="font-bold text-lg group-hover:text-primary transition-colors">{dataset.name}</h3>
                    <p className="text-xs text-slate-500 font-mono mt-1">s3://fds-data/{deviceName}/{shotId}/{dataset.name}.zarr</p>
                 </div>
              </div>
              <ChevronRight className="text-slate-600 group-hover:text-primary opacity-0 group-hover:opacity-100 transition-all" />
            </div>

            <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
                <div className="flex items-center gap-1">
                    <FileCode className="w-4 h-4" />
                    Zarr / Icechunk
                </div>
                <div className="text-emerald-400 text-xs px-2 py-0.5 bg-emerald-500/10 rounded-full border border-emerald-500/20">
                    Verified
                </div>
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
