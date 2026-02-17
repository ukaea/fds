'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Database, Server, Search, Filter } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Device } from '@/lib/types';

export default function DatasetsPage() {
  const { data: devices, error: devicesError, isLoading: devicesLoading } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'global' | 'device'>('all');

  // Filter devices based on search query
  const filteredDevices = devices?.filter(device => 
    device.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    device.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Datasets</h1>
          <p className="text-slate-400">Browse global and device-specific datasets.</p>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search devices or datasets..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-900/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setFilterType('all')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'all' 
                ? 'bg-blue-500 text-white' 
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilterType('global')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'global' 
                ? 'bg-emerald-500 text-white' 
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            Global
          </button>
          <button
            onClick={() => setFilterType('device')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'device' 
                ? 'bg-purple-500 text-white' 
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            Device-Linked
          </button>
        </div>
      </div>

      {/* Global Datasets Section */}
      {(filterType === 'all' || filterType === 'global') && (
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-emerald-500/20 p-2 rounded-lg text-emerald-400">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-white">Global Datasets</h2>
            <span className="text-sm text-slate-500">(Standalone, not linked to devices)</span>
          </div>
          <div className="card p-6">
            <div className="text-center py-8 text-slate-400">
              <p className="text-sm">No global datasets available yet.</p>
              <p className="text-xs mt-2 text-slate-500">Global datasets will appear here when added to the system.</p>
            </div>
          </div>
        </div>
      )}

      {/* Device-Linked Datasets Section */}
      {(filterType === 'all' || filterType === 'device') && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-purple-500/20 p-2 rounded-lg text-purple-400">
              <Server className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-white">Devices & Their Datasets</h2>
            <span className="text-sm text-slate-500">(Device-level and shot-level datasets)</span>
          </div>

          {devicesLoading && (
            <div className="card p-6 text-center text-slate-400">
              Loading devices...
            </div>
          )}

          {devicesError && (
            <div className="card p-6 text-center text-red-400">
              Failed to load devices
            </div>
          )}

          {!devicesLoading && !devicesError && filteredDevices && filteredDevices.length === 0 && (
            <div className="card p-6 text-center text-slate-400">
              <p className="text-sm">
                {searchQuery ? 'No devices match your search.' : 'No devices registered yet.'}
              </p>
              {!searchQuery && (
                <Link href="/devices" className="inline-block mt-4 text-blue-400 hover:text-blue-300 text-sm">
                  Register your first device →
                </Link>
              )}
            </div>
          )}

          {!devicesLoading && !devicesError && filteredDevices && filteredDevices.length > 0 && (
            <div className="space-y-4">
              {filteredDevices.map((device) => (
                <div key={device.name} className="card overflow-hidden">
                  <div className="p-6 bg-slate-800/30">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="bg-blue-500/20 p-2 rounded-lg text-blue-400">
                          <Server className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="text-lg font-semibold text-white">{device.name}</h3>
                          <p className="text-sm text-slate-400">
                            {device.description || 'No description available'}
                          </p>
                        </div>
                      </div>
                      <Link
                        href={`/devices/${device.name}/shots`}
                        className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors"
                      >
                        View Shots
                      </Link>
                    </div>
                  </div>
                  <div className="p-6">
                    <div className="text-sm text-slate-400 mb-3">
                      <span className="font-medium text-slate-300">Device Datasets:</span>
                    </div>
                    <div className="text-center py-6 bg-slate-900/30 rounded-lg border border-dashed border-slate-700">
                      <p className="text-sm text-slate-500">No device-level datasets available for {device.name}.</p>
                      <p className="text-xs text-slate-600 mt-1">
                        Navigate to shots to view shot-level datasets.
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
