'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, Shot } from '@/lib/types';
import { useDeviceLabel } from '@/lib/use-device-label';
import { Calendar, Database, ChevronRight, Server } from 'lucide-react';
import { ClientDate } from '@/components/client-date';
import { DeviceDatasets } from '@/components/device-datasets';

type Tab = 'shots' | 'datasets';

export default function DeviceDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const deviceLabel = useDeviceLabel(deviceName);
  const [activeTab, setActiveTab] = useState<Tab>('shots');

  const { data: shots, error: shotsError, isLoading: shotsLoading } = useSWR<Shot[]>(
    deviceName ? `${API_BASE}/devices/${deviceName}/shots/` : null,
    fetcher
  );

  const { data: datasets, error: datasetsError, isLoading: datasetsLoading } = useSWR<Dataset[]>(
    deviceName ? `${API_BASE}/devices/${deviceName}/datasets?scope=device` : null,
    fetcher
  );

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center text-sm text-muted-foreground mb-2">
          <Link href="/devices" className="hover:text-primary transition-colors">Devices</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-foreground font-medium">{deviceLabel}</span>
        </div>
        <div className="flex items-center gap-3 mb-2">
          <div className="bg-muted p-2 rounded-lg text-foreground">
            <Server className="w-6 h-6" />
          </div>
          <h1 className="text-3xl font-bold text-foreground">{deviceLabel}</h1>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-border">
        <button
          onClick={() => setActiveTab('shots')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
            activeTab === 'shots'
              ? 'text-foreground border-primary bg-muted/50'
              : 'text-muted-foreground border-transparent hover:text-foreground hover:border-border'
          }`}
        >
          Shots
          {shots && (
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
              activeTab === 'shots' ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
            }`}>
              {shots.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('datasets')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
            activeTab === 'datasets'
              ? 'text-foreground border-primary bg-muted/50'
              : 'text-muted-foreground border-transparent hover:text-foreground hover:border-border'
          }`}
        >
          Device Datasets
          {datasets && datasets.length > 0 && (
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
              activeTab === 'datasets' ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
            }`}>
              {datasets.length}
            </span>
          )}
        </button>
      </div>

      {/* Shots Tab */}
      {activeTab === 'shots' && (
        <div className="space-y-4">
          {shotsLoading && <div className="py-8 text-muted-foreground">Loading shots...</div>}
          {shotsError && <div className="py-8 text-destructive">Failed to load shots.</div>}
          {!shotsLoading && !shotsError && shots?.map((shot) => (
            <Link
              key={shot.id}
              href={`/devices/${deviceName}/shots/${shot.id}`}
              className="block card p-6 hover:bg-muted transition-colors group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="bg-muted text-foreground px-3 py-1 rounded-full text-xs font-mono font-bold">
                      #{shot.id}
                    </span>
                    <span className="text-foreground font-medium">Standard Plasma Experiment</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground mt-2">
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
                <ChevronRight className="text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
              </div>
            </Link>
          ))}
          {!shotsLoading && !shotsError && (!shots || shots.length === 0) && (
            <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
              No shots found for this device.
            </div>
          )}
        </div>
      )}

      {/* Device Datasets Tab */}
      {activeTab === 'datasets' && (
        <div>
          {datasetsLoading && <div className="py-8 text-muted-foreground">Loading datasets...</div>}
          {datasetsError && <div className="py-8 text-destructive">Failed to load datasets.</div>}
          {!datasetsLoading && !datasetsError && datasets && datasets.length > 0 && (
            <DeviceDatasets datasets={datasets} deviceName={deviceName} />
          )}
          {!datasetsLoading && !datasetsError && (!datasets || datasets.length === 0) && (
            <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
              <Database className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No device-level datasets registered.</p>
              <p className="text-sm mt-1 text-muted-foreground">Device datasets are not tied to a specific shot — useful for calibration data, geometry files, and wall configurations.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
