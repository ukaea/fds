'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Activity, ArrowLeft, ChevronRight, Server, Globe, Link2 } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Source, Device } from '@/lib/types';

export default function SourceDetailPage() {
  const params = useParams();
  const sourceName = params.name as string;

  const { data: source, error, isLoading } = useSWR<Source>(
    sourceName ? `${API_BASE}/sources/${sourceName}` : null,
    fetcher
  );

  // Fetch all devices to resolve device_id -> device name
  const { data: devices } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);

  // Find the device name for this source (if device-linked)
  // We need to match device by ID - since Device type doesn't have ID in the frontend type,
  // we'll fetch device sources for each device to find the match.
  // Actually, the simplest approach: fetch all devices and check which one has this source.
  // But the SourceRead model only returns device_id, not device_name.
  // For now, we show the device_id info and can enhance later.

  if (error) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link href="/sources" className="inline-flex items-center text-sm text-slate-400 hover:text-white mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sources
        </Link>
        <div className="card p-8 text-center text-red-400">
          Failed to load source &quot;{sourceName}&quot;
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-12 text-slate-400">
        Loading source details...
      </div>
    );
  }

  if (!source) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link href="/sources" className="inline-flex items-center text-sm text-slate-400 hover:text-white mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sources
        </Link>
        <div className="card p-8 text-center text-slate-400">
          Source &quot;{sourceName}&quot; not found.
        </div>
      </div>
    );
  }

  const isDeviceLinked = !!source.device_id;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Navigation */}
      <div className="mb-8">
        <Link href="/sources" className="inline-flex items-center text-sm text-slate-400 hover:text-white mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sources
        </Link>
        <div className="flex items-center text-sm text-slate-400 mb-2">
          <Link href="/sources" className="hover:text-primary transition-colors">Sources</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-white font-medium">{source.name}</span>
        </div>
      </div>

      {/* Source Header */}
      <div className="card overflow-hidden mb-8">
        <div className={`h-1.5 w-full ${
          isDeviceLinked
            ? 'bg-gradient-to-r from-purple-500 to-blue-500'
            : 'bg-gradient-to-r from-emerald-500 to-blue-500'
        }`} />
        <div className="p-8">
          <div className="flex items-start gap-4 mb-6">
            <div className={`p-3 rounded-xl ${
              isDeviceLinked
                ? 'bg-purple-500/20 text-purple-400'
                : 'bg-emerald-500/20 text-emerald-400'
            }`}>
              <Activity className="w-8 h-8" />
            </div>
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-white mb-2">{source.name}</h1>
              <span className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border font-medium ${
                isDeviceLinked
                  ? 'text-purple-400 bg-purple-500/10 border-purple-500/20'
                  : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
              }`}>
                {isDeviceLinked ? (
                  <><Server className="w-3 h-3" /> Device-Linked Source</>
                ) : (
                  <><Globe className="w-3 h-3" /> Global Source</>
                )}
              </span>
            </div>
          </div>

          {source.description ? (
            <p className="text-slate-300 text-lg leading-relaxed">{source.description}</p>
          ) : (
            <p className="text-slate-500 italic">No description available for this source.</p>
          )}
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Metadata Card */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Link2 className="w-5 h-5 text-slate-400" />
            Source Information
          </h2>
          <div className="space-y-4">
            <div>
              <dt className="text-sm text-slate-500 mb-1">Name</dt>
              <dd className="text-white font-mono text-sm bg-slate-900/50 px-3 py-2 rounded-lg">
                {source.name}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-slate-500 mb-1">Scope</dt>
              <dd className="text-white text-sm">
                {isDeviceLinked ? `Device-Linked (ID: ${source.device_id})` : 'Global'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-slate-500 mb-1">Internal ID</dt>
              <dd className="text-slate-400 font-mono text-sm">{source.id}</dd>
            </div>
          </div>
        </div>

        {/* Provenance Info Card */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-slate-400" />
            Provenance
          </h2>
          <div className="text-center py-8 bg-slate-900/30 rounded-lg border border-dashed border-slate-700">
            <p className="text-sm text-slate-500">
              Linked datasets and provenance details will be available in a future release.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
