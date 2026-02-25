'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Activity, Search, Server, Globe, ChevronRight } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Device, Source } from '@/lib/types';

export default function SourcesPage() {
  const { data: sources, error: sourcesError, isLoading: sourcesLoading } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);
  const { data: devices } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'global' | 'device'>('all');

  // Build device lookup map: id -> name
  const deviceMap = new Map<number, string>();
  devices?.forEach(d => {
    // We need the device id, but Device type only has name.
    // Since sources have device_id, we fetch devices and match by iterating.
    // For now we'll use the devices list to enrich source display.
  });

  // Filter sources based on search and scope filter
  const filteredSources = sources?.filter(source => {
    const matchesSearch = !searchQuery ||
      source.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      source.description?.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesFilter =
      filterType === 'all' ||
      (filterType === 'global' && !source.device_id) ||
      (filterType === 'device' && !!source.device_id);

    return matchesSearch && matchesFilter;
  });

  const globalSources = filteredSources?.filter(s => !s.device_id) || [];
  const deviceSources = filteredSources?.filter(s => !!s.device_id) || [];

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Data Sources</h1>
          <p className="text-slate-400">
            Diagnostic instruments, simulation codes, and data producers in the FDS ecosystem.
          </p>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search sources by name or description..."
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

      {/* Loading State */}
      {sourcesLoading && (
        <div className="card p-8 text-center text-slate-400">
          Loading sources...
        </div>
      )}

      {/* Error State */}
      {sourcesError && (
        <div className="card p-8 text-center text-red-400">
          Failed to load sources
        </div>
      )}

      {/* Empty State */}
      {!sourcesLoading && !sourcesError && (!filteredSources || filteredSources.length === 0) && (
        <div className="text-center py-16 bg-slate-800/30 rounded-lg border border-dashed border-slate-700">
          <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
            <div className="bg-slate-700/50 p-4 rounded-full">
              <Activity className="w-12 h-12 text-slate-400" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white mb-2">
                {searchQuery ? 'No Matching Sources' : 'No Sources Registered Yet'}
              </h3>
              <p className="text-slate-400">
                {searchQuery
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Sources represent diagnostic instruments and simulation codes that produce data. They will appear here once registered via the API.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Sources List */}
      {!sourcesLoading && !sourcesError && filteredSources && filteredSources.length > 0 && (
        <div className="space-y-8">
          {/* Global Sources */}
          {(filterType === 'all' || filterType === 'global') && globalSources.length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="bg-emerald-500/20 p-2 rounded-lg text-emerald-400">
                  <Globe className="w-5 h-5" />
                </div>
                <h2 className="text-xl font-semibold text-white">Global Sources</h2>
                <span className="text-sm text-slate-500">({globalSources.length})</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {globalSources.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            </div>
          )}

          {/* Device-Linked Sources */}
          {(filterType === 'all' || filterType === 'device') && deviceSources.length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="bg-purple-500/20 p-2 rounded-lg text-purple-400">
                  <Server className="w-5 h-5" />
                </div>
                <h2 className="text-xl font-semibold text-white">Device-Linked Sources</h2>
                <span className="text-sm text-slate-500">({deviceSources.length})</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {deviceSources.map((source) => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SourceCard({ source }: { source: Source }) {
  return (
    <Link
      href={`/sources/${source.name}`}
      className="card p-6 group hover:bg-slate-800/50 transition-colors block"
    >
      <div className="flex items-start gap-3 mb-3">
        <div className={`p-2 rounded-lg ${
          source.device_id
            ? 'bg-purple-500/20 text-purple-400'
            : 'bg-emerald-500/20 text-emerald-400'
        }`}>
          <Activity className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-white mb-1 truncate group-hover:text-primary transition-colors">
            {source.name}
          </h3>
          <p className="text-sm text-slate-400 line-clamp-2">
            {source.description || 'No description available'}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-4">
        <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
          source.device_id
            ? 'text-purple-400 bg-purple-500/10 border-purple-500/20'
            : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
        }`}>
          {source.device_id ? 'Device-Linked' : 'Global'}
        </span>
        <div className="flex items-center text-xs text-slate-500 group-hover:text-primary transition-colors font-medium">
          View Details <ChevronRight className="w-3.5 h-3.5 ml-1 group-hover:translate-x-0.5 transition-transform" />
        </div>
      </div>

      {/* Bottom accent bar */}
      <div className={`h-0.5 w-full mt-4 rounded-full transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left ${
        source.device_id
          ? 'bg-gradient-to-r from-purple-500 to-blue-500'
          : 'bg-gradient-to-r from-emerald-500 to-blue-500'
      }`} />
    </Link>
  );
}
