'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Database, Server, Search } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Device, Dataset } from '@/lib/types';
import { annotationFacets, annotationQuery, withQuery } from '@/lib/features';
import { AnnotationFilter } from '@/components/annotation-filter';
import { DatasetCard } from '@/components/dataset-card';
import { DatasetResults } from '@/components/dataset-results';
import { DeviceDatasets } from '@/components/device-datasets';

export default function DatasetsPage() {
  const { data: devices, error: devicesError, isLoading: devicesLoading } = useSWR<Device[]>(
    `${API_BASE}/devices/`,
    fetcher
  );
  const ALL_DATASETS = `${API_BASE}/datasets?limit=1000`;
  const { data: allDatasets } = useSWR<Dataset[]>(ALL_DATASETS, fetcher);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'global' | 'device'>('all');
  const [annotations, setAnnotations] = useState<string[]>([]);

  // Only the dataset's own annotations here. Filtering on a parent shot's would
  // need the shots of every device, and shots are only listed under one.
  const { data: annotated, isLoading: annotatedLoading } = useSWR<Dataset[]>(
    annotations.length > 0
      ? withQuery(ALL_DATASETS, annotationQuery('annotation', annotations))
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  const query = searchQuery.toLowerCase();
  const matches = (text?: string) => (text ?? '').toLowerCase().includes(query);

  const globalDatasets = (allDatasets ?? []).filter((d) => !d.device_name && matches(d.name));
  const filteredDevices = devices?.filter(
    (device) => matches(device.name) || matches(device.title) || matches(device.description)
  );
  // Device-level datasets only (shot-level datasets live under each shot).
  const deviceDatasets = (name: string) =>
    (allDatasets ?? []).filter((d) => d.device_name === name && !d.shot_id);

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2">Datasets</h1>
          <p className="text-muted-foreground">Browse global and device-specific datasets.</p>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search devices or datasets..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-card/50 border border-border rounded-lg text-foreground placeholder-muted-foreground focus:outline-none focus:border-border transition-colors"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setFilterType('all')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'all' ? 'bg-muted text-foreground' : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilterType('global')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'global' ? 'bg-muted text-foreground' : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            Global
          </button>
          <button
            onClick={() => setFilterType('device')}
            className={`px-4 py-2 rounded-lg transition-colors ${
              filterType === 'device' ? 'bg-muted text-foreground' : 'bg-muted text-muted-foreground hover:bg-muted'
            }`}
          >
            Device-Linked
          </button>
        </div>
      </div>

      <AnnotationFilter
        label="Filter by annotation"
        facets={annotationFacets(allDatasets)}
        selected={annotations}
        onChange={setAnnotations}
      />

      {/* An annotation filter is a query, not a browse, so it answers with one
          flat list. The sections below are organised by where a dataset sits,
          which would hide the shot-level matches entirely. */}
      {annotations.length > 0 && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-foreground">Matching Datasets</h2>
            <span className="text-sm text-muted-foreground">
              ({annotated?.length ?? 0} of {allDatasets?.length ?? 0})
            </span>
          </div>
          {annotatedLoading && !annotated ? (
            <div className="card p-6 text-center text-muted-foreground">Loading datasets...</div>
          ) : (
            <DatasetResults
              datasets={annotated}
              emptyMessage="No datasets carry every selected annotation."
            />
          )}
        </div>
      )}

      {/* Global Datasets Section */}
      {annotations.length === 0 && (filterType === 'all' || filterType === 'global') && (
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-foreground">Global Datasets</h2>
            <span className="text-sm text-muted-foreground">(Standalone, not linked to devices)</span>
          </div>
          {globalDatasets.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {globalDatasets.map((dataset) => (
                <DatasetCard key={dataset.id} dataset={dataset} />
              ))}
            </div>
          ) : (
            <div className="card p-6">
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">No global datasets available.</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Device-Linked Datasets Section */}
      {annotations.length === 0 && (filterType === 'all' || filterType === 'device') && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Server className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-foreground">Devices &amp; Their Datasets</h2>
            <span className="text-sm text-muted-foreground">(Device-level datasets)</span>
          </div>

          {devicesLoading && (
            <div className="card p-6 text-center text-muted-foreground">Loading devices...</div>
          )}
          {devicesError && (
            <div className="card p-6 text-center text-destructive">Failed to load devices</div>
          )}

          {!devicesLoading && !devicesError && filteredDevices && filteredDevices.length === 0 && (
            <div className="card p-6 text-center text-muted-foreground">
              <p className="text-sm">
                {searchQuery ? 'No devices match your search.' : 'No devices registered yet.'}
              </p>
              {!searchQuery && (
                <Link href="/devices" className="inline-block mt-4 text-foreground hover:text-foreground text-sm">
                  Register your first device →
                </Link>
              )}
            </div>
          )}

          {!devicesLoading && !devicesError && filteredDevices && filteredDevices.length > 0 && (
            <div className="space-y-4">
              {filteredDevices.map((device) => {
                const datasets = deviceDatasets(device.name);
                return (
                  <div key={device.name} className="card overflow-hidden">
                    <div className="p-6 bg-muted/30">
                      <div className="flex items-center justify-between">
                        <Link href={`/devices/${device.name}`} className="flex items-center gap-3 group">
                          <div className="bg-muted p-2 rounded-lg text-foreground">
                            <Server className="w-5 h-5" />
                          </div>
                          <div>
                            <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">
                              {device.title || device.name}
                            </h3>
                            <p className="text-sm text-muted-foreground">
                              {device.description || 'No description available'}
                            </p>
                          </div>
                        </Link>
                        <Link
                          href={`/devices/${device.name}/shots`}
                          className="px-4 py-2 bg-muted hover:bg-accent text-foreground text-sm rounded-lg transition-colors"
                        >
                          View Shots
                        </Link>
                      </div>
                    </div>
                    <div className="p-6">
                      <div className="text-sm text-muted-foreground mb-3">
                        <span className="font-medium text-foreground">Device Datasets:</span>
                      </div>
                      {datasets.length > 0 ? (
                        <DeviceDatasets datasets={datasets} />
                      ) : (
                        <div className="text-center py-6 bg-card/30 rounded-lg border border-dashed border-border">
                          <p className="text-sm text-muted-foreground">
                            No device-level datasets for {device.title || device.name}.
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            Navigate to shots to view shot-level datasets.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
