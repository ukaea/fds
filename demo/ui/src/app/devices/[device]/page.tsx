'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, Shot } from '@/lib/types';
import { Calendar, Database, FileCode, ChevronRight, Server } from 'lucide-react';
import { ClientDate } from '@/components/client-date';

type Tab = 'shots' | 'datasets';

export default function DeviceDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const [activeTab, setActiveTab] = useState<Tab>('shots');

  const { data: shots, error: shotsError, isLoading: shotsLoading } = useSWR<Shot[]>(
    deviceName ? `${API_BASE}/devices/${deviceName}/shots/` : null,
    fetcher
  );

  const { data: datasets, error: datasetsError, isLoading: datasetsLoading } = useSWR<Dataset[]>(
    deviceName ? `${API_BASE}/devices/${deviceName}/datasets` : null,
    fetcher
  );

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center text-sm text-slate-400 mb-2">
          <Link href="/devices" className="hover:text-primary transition-colors">Devices</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-white font-medium">{deviceName}</span>
        </div>
        <div className="flex items-center gap-3 mb-2">
          <div className="bg-blue-500/20 p-2 rounded-lg text-blue-400">
            <Server className="w-6 h-6" />
          </div>
          <h1 className="text-3xl font-bold text-white">{deviceName}</h1>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-700">
        <button
          onClick={() => setActiveTab('shots')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
            activeTab === 'shots'
              ? 'text-white border-primary bg-slate-800/50'
              : 'text-slate-400 border-transparent hover:text-slate-200 hover:border-slate-500'
          }`}
        >
          Shots
          {shots && (
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
              activeTab === 'shots' ? 'bg-primary/20 text-primary' : 'bg-slate-700 text-slate-400'
            }`}>
              {shots.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('datasets')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
            activeTab === 'datasets'
              ? 'text-white border-primary bg-slate-800/50'
              : 'text-slate-400 border-transparent hover:text-slate-200 hover:border-slate-500'
          }`}
        >
          Device Datasets
          {datasets && datasets.length > 0 && (
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
              activeTab === 'datasets' ? 'bg-primary/20 text-primary' : 'bg-slate-700 text-slate-400'
            }`}>
              {datasets.length}
            </span>
          )}
        </button>
      </div>

      {/* Shots Tab */}
      {activeTab === 'shots' && (
        <div className="space-y-4">
          {shotsLoading && <div className="py-8 text-slate-400">Loading shots...</div>}
          {shotsError && <div className="py-8 text-red-400">Failed to load shots.</div>}
          {!shotsLoading && !shotsError && shots?.map((shot) => (
            <Link
              key={shot.id}
              href={`/devices/${deviceName}/shots/${shot.id}`}
              className="block card p-6 hover:bg-slate-800/50 transition-colors group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="bg-emerald-500/20 text-emerald-400 px-3 py-1 rounded-full text-xs font-mono font-bold">
                      #{shot.id}
                    </span>
                    <span className="text-slate-300 font-medium">Standard Plasma Experiment</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-slate-500 mt-2">
                    <div className="flex items-center gap-1">
                      <Calendar className="w-4 h-4" />
                      <ClientDate timestamp={shot.timestamp} />
                    </div>
                    <div className="flex items-center gap-1">
                      <Database className="w-4 h-4" />
                      Metadata Available
                    </div>
                  </div>
                </div>
                <ChevronRight className="text-slate-600 group-hover:text-primary group-hover:translate-x-1 transition-all" />
              </div>
            </Link>
          ))}
          {!shotsLoading && !shotsError && (!shots || shots.length === 0) && (
            <div className="text-center py-12 text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-slate-700">
              No shots found for this device.
            </div>
          )}
        </div>
      )}

      {/* Device Datasets Tab */}
      {activeTab === 'datasets' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {datasetsLoading && <div className="col-span-full py-8 text-slate-400">Loading datasets...</div>}
          {datasetsError && <div className="col-span-full py-8 text-red-400">Failed to load datasets.</div>}
          {!datasetsLoading && !datasetsError && datasets?.map((dataset) => (
            <Link
              key={dataset.name}
              href={`/devices/${deviceName}/datasets/${dataset.name}`}
              className="card p-6 hover:border-primary/50 transition-all group"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="bg-purple-500/20 p-2 rounded text-purple-400">
                    <Database className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-lg group-hover:text-primary transition-colors">{dataset.name}</h3>
                    {dataset.url && (
                      <p className="text-xs text-slate-500 font-mono mt-1">{dataset.url}</p>
                    )}
                  </div>
                </div>
                <ChevronRight className="text-slate-600 group-hover:text-primary opacity-0 group-hover:opacity-100 transition-all" />
              </div>
              <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
                <div className="flex items-center gap-1">
                  <FileCode className="w-4 h-4" />
                  {dataset.media_type || 'Dataset'}
                </div>
                {dataset.level !== undefined && (
                  <span className="text-xs px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded-full border border-blue-500/20">
                    Level {dataset.level}
                  </span>
                )}
              </div>
            </Link>
          ))}
          {!datasetsLoading && !datasetsError && (!datasets || datasets.length === 0) && (
            <div className="col-span-full text-center py-12 text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-slate-700">
              <Database className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No device-level datasets registered.</p>
              <p className="text-sm mt-1 text-slate-600">Device datasets are not tied to a specific shot — useful for calibration data, geometry files, and wall configurations.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
