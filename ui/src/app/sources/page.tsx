'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Activity, Search, Server, Globe, ChevronRight } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Source } from '@/lib/types';

export default function SourcesPage() {
  const { data: sources, error: sourcesError, isLoading: sourcesLoading } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'global' | 'device'>('all');

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
          <h1 className="text-3xl font-bold text-foreground mb-2">Data Sources</h1>
          <p className="text-muted-foreground">
            Diagnostic instruments, simulation codes, and data producers in the FDS ecosystem.
          </p>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search sources by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-card/50 border border-border rounded-lg text-foreground placeholder-muted-foreground focus:outline-none focus:border-border transition-colors"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setFilterType('all')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'all'
                ? 'bg-muted text-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilterType('global')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'global'
                ? 'bg-muted text-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            Global
          </button>
          <button
            onClick={() => setFilterType('device')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'device'
                ? 'bg-muted text-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            Device-Linked
          </button>
        </div>
      </div>

      {/* Loading State */}
      {sourcesLoading && (
        <div className="card p-8 text-center text-muted-foreground">
          Loading sources...
        </div>
      )}

      {/* Error State */}
      {sourcesError && (
        <div className="card p-8 text-center text-destructive">
          Failed to load sources
        </div>
      )}

      {/* Empty State */}
      {!sourcesLoading && !sourcesError && (!filteredSources || filteredSources.length === 0) && (
        <div className="text-center py-16 bg-muted/30 rounded-lg border border-dashed border-border">
          <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
            <div className="bg-muted/50 p-4 rounded-full">
              <Activity className="w-12 h-12 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-2">
                {searchQuery ? 'No Matching Sources' : 'No Sources Registered Yet'}
              </h3>
              <p className="text-muted-foreground">
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
                <div className="bg-muted p-2 rounded-lg text-foreground">
                  <Globe className="w-5 h-5" />
                </div>
                <h2 className="text-xl font-semibold text-foreground">Global Sources</h2>
                <span className="text-sm text-muted-foreground">({globalSources.length})</span>
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
                <div className="bg-muted p-2 rounded-lg text-foreground">
                  <Server className="w-5 h-5" />
                </div>
                <h2 className="text-xl font-semibold text-foreground">Device-Linked Sources</h2>
                <span className="text-sm text-muted-foreground">({deviceSources.length})</span>
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
      href={`/sources/${source.id}`}
      className="card p-6 group hover:bg-muted transition-colors block"
    >
      <div className="flex items-start gap-3 mb-3">
        <div className={`p-2 rounded-lg ${
          source.device_id
            ? 'bg-muted text-foreground'
            : 'bg-muted text-foreground'
        }`}>
          <Activity className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-foreground mb-1 truncate group-hover:text-primary transition-colors">
            {source.name}
          </h3>
          <p className="text-sm text-muted-foreground line-clamp-2">
            {source.description || 'No description available'}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-4">
        <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
          source.device_id
            ? 'text-foreground bg-muted border-border'
            : 'text-foreground bg-muted border-border'
        }`}>
          {source.device_id ? 'Device-Linked' : 'Global'}
        </span>
        <div className="flex items-center text-xs text-muted-foreground group-hover:text-primary transition-colors font-medium">
          View Details <ChevronRight className="w-3.5 h-3.5 ml-1 group-hover:translate-x-0.5 transition-transform" />
        </div>
      </div>

      {/* Bottom accent bar */}
      <div className={`h-0.5 w-full mt-4 rounded-full transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left ${
        source.device_id
          ? 'bg-gradient-to-r from-muted to-muted'
          : 'bg-gradient-to-r from-muted to-muted'
      }`} />
    </Link>
  );
}
