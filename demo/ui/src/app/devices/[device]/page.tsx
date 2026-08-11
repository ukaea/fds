'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, Shot } from '@/lib/types';
import { Database, ChevronRight, Server } from 'lucide-react';
import { useDeviceLabel } from '@/lib/use-device-label';
import { annotationFacets, annotationQuery, withQuery } from '@/lib/features';
import { AnnotationFilter } from '@/components/annotation-filter';
import { DatasetResults } from '@/components/dataset-results';
import { DeviceDatasets } from '@/components/device-datasets';
import { ShotList, shotsUrl } from '@/components/shot-list';

type Tab = 'shots' | 'shot-datasets' | 'datasets';

function TabButton({
  active,
  count,
  onClick,
  children,
}: {
  active: boolean;
  count?: number;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
        active
          ? 'text-foreground border-primary bg-muted/50'
          : 'text-muted-foreground border-transparent hover:text-foreground hover:border-border'
      }`}
    >
      {children}
      {count != null && count > 0 && (
        <span
          className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
            active ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * The device's shot-level datasets, filterable on their own annotations and on
 * those of the shot they belong to. The second is the cross-level question:
 * "the equilibrium datasets from shots that had ELMs" is one request, not a shot
 * query followed by a request per shot.
 *
 * Scoped to shot-level datasets deliberately. A device-level dataset has no
 * parent shot, so it could never satisfy a shot annotation filter.
 */
function ShotDatasets({ deviceName, shots }: { deviceName: string; shots?: Shot[] }) {
  const [annotations, setAnnotations] = useState<string[]>([]);
  const [shotAnnotations, setShotAnnotations] = useState<string[]>([]);

  const baseUrl = `${API_BASE}/devices/${deviceName}/datasets?scope=shot`;
  const { data: allDatasets } = useSWR<Dataset[]>(deviceName ? baseUrl : null, fetcher);

  // keepPreviousData so the list settles under the chips rather than blanking.
  const { data: datasets, error, isLoading } = useSWR<Dataset[]>(
    deviceName
      ? withQuery(
          baseUrl,
          annotationQuery('annotation', annotations),
          annotationQuery('shot_annotation', shotAnnotations)
        )
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  const filtered = annotations.length > 0 || shotAnnotations.length > 0;

  if (error) return <div className="py-8 text-destructive">Failed to load datasets.</div>;
  if (isLoading && !datasets) {
    return <div className="py-8 text-muted-foreground">Loading datasets...</div>;
  }

  return (
    <div>
      <AnnotationFilter
        label="Filter by dataset annotation"
        facets={annotationFacets(allDatasets)}
        selected={annotations}
        onChange={setAnnotations}
      />
      <AnnotationFilter
        label="Filter by shot annotation"
        facets={annotationFacets(shots)}
        selected={shotAnnotations}
        onChange={setShotAnnotations}
      />

      {filtered && (
        <p className="text-sm text-muted-foreground mb-4">
          {datasets?.length ?? 0} of {allDatasets?.length ?? 0} datasets
        </p>
      )}

      <DatasetResults
        datasets={datasets}
        emptyMessage={
          filtered
            ? 'No shot datasets match every selected annotation.'
            : 'No shot-level datasets for this device.'
        }
      />
    </div>
  );
}

export default function DeviceDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const deviceLabel = useDeviceLabel(deviceName);
  const [activeTab, setActiveTab] = useState<Tab>('shots');

  // Shared with ShotList below (same url, so SWR makes one request) and used
  // here for the tab count and for the shot annotation chips on the datasets tab.
  const { data: shots } = useSWR<Shot[]>(deviceName ? shotsUrl(deviceName) : null, fetcher);

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
        <TabButton
          active={activeTab === 'shots'}
          count={shots?.length}
          onClick={() => setActiveTab('shots')}
        >
          Shots
        </TabButton>
        <TabButton
          active={activeTab === 'shot-datasets'}
          onClick={() => setActiveTab('shot-datasets')}
        >
          Shot Datasets
        </TabButton>
        <TabButton
          active={activeTab === 'datasets'}
          count={datasets?.length}
          onClick={() => setActiveTab('datasets')}
        >
          Device Datasets
        </TabButton>
      </div>

      {activeTab === 'shots' && <ShotList deviceName={deviceName} />}

      {activeTab === 'shot-datasets' && <ShotDatasets deviceName={deviceName} shots={shots} />}

      {/* Device Datasets Tab */}
      {activeTab === 'datasets' && (
        <div>
          {datasetsLoading && <div className="py-8 text-muted-foreground">Loading datasets...</div>}
          {datasetsError && <div className="py-8 text-destructive">Failed to load datasets.</div>}
          {!datasetsLoading && !datasetsError && datasets && datasets.length > 0 && (
            <DeviceDatasets datasets={datasets} />
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
