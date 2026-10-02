'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { fetcher, API_BASE } from '@/lib/api';
import { AvailableProperties, Dataset } from '@/lib/types';
import { Database, ChevronRight, Server } from 'lucide-react';
import { useDeviceLabel } from '@/lib/use-device-label';
import { availableProperties, propertyQuery, withQuery } from '@/lib/properties';
import { PropertyFilter } from '@/components/property-filter';
import { DatasetResults } from '@/components/dataset-results';
import { SidePanelLayout } from '@/components/side-panel-layout';
import { LoadMore } from '@/components/load-more';
import { usePagedList } from '@/lib/use-paged-list';
import { DeviceDatasets } from '@/components/device-datasets';
import { ShotList, shotPropertiesUrl } from '@/components/shot-list';
import { JsonLdPanel } from '@/components/jsonld-panel';

type Tab = 'shots' | 'shot-datasets' | 'datasets';

const DATASET_PAGE_SIZE = 100;

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
 * The device's shot-level datasets, filterable on their own properties and on
 * those of the shot they belong to. The second is the cross-level question:
 * "the equilibrium datasets from shots that had ELMs" is one request, not a shot
 * query followed by a request per shot.
 *
 * Scoped to shot-level datasets deliberately. A device-level dataset has no
 * parent shot, so it could never satisfy a shot annotation filter.
 */
function ShotDatasets({
  deviceName,
  aside,
}: {
  deviceName: string;
  aside?: React.ReactNode;
}) {
  const [propertyTokens, setPropertyTokens] = useState<string[]>([]);
  const [shotPropertyTokens, setShotPropertyTokens] = useState<string[]>([]);

  // The shot chips describe every shot on the device, not the hundred a
  // listing would return. Same SWR key as ShotList and the tab count above,
  // so all three share one request.
  const { data: shotProperties } = useSWR<AvailableProperties>(
    deviceName ? shotPropertiesUrl(deviceName) : null,
    fetcher
  );

  const baseUrl = `${API_BASE}/devices/${deviceName}/datasets?scope=shot`;
  // The dataset chips are read from this first page alone, since no endpoint
  // aggregates dataset properties across a device.
  const { data: firstPage } = useSWR<Dataset[]>(deviceName ? baseUrl : null, fetcher);
  const datasetProperties = availableProperties(firstPage);
  const shotPropertyList = shotProperties?.properties ?? [];

  const {
    items: datasets,
    error,
    isLoading,
    done,
    loadingMore,
    loadMore,
  } = usePagedList<Dataset>(
    deviceName
      ? withQuery(
          baseUrl,
          propertyQuery('property', propertyTokens),
          propertyQuery('shot_property', shotPropertyTokens)
        )
      : null,
    DATASET_PAGE_SIZE
  );

  const filtered = propertyTokens.length > 0 || shotPropertyTokens.length > 0;

  if (error) return <div className="py-8 text-destructive">Failed to load datasets.</div>;
  if (isLoading && !datasets) {
    return <div className="py-8 text-muted-foreground">Loading datasets...</div>;
  }

  return (
    <SidePanelLayout
      side={
        (datasetProperties.length > 0 || shotPropertyList.length > 0 || aside) && (
          <>
            <PropertyFilter
              label="Filter by dataset property"
              properties={datasetProperties}
              selected={propertyTokens}
              onChange={setPropertyTokens}
            />
            <PropertyFilter
              label="Filter by shot property"
              properties={shotPropertyList}
              selected={shotPropertyTokens}
              onChange={setShotPropertyTokens}
            />
            {aside}
          </>
        )
      }
    >
      <DatasetResults
        datasets={datasets}
        emptyMessage={
          filtered
            ? 'No shot datasets match every selected annotation.'
            : 'No shot-level datasets for this device.'
        }
      />
      {datasets && datasets.length > 0 && (
        <LoadMore onLoad={loadMore} loading={loadingMore} done={done} />
      )}
    </SidePanelLayout>
  );
}

export default function DeviceDetail({ deviceName }: { deviceName: string }) {
  const deviceLabel = useDeviceLabel(deviceName);
  const [activeTab, setActiveTab] = useState<Tab>('shots');

  // Shared with ShotList and ShotDatasets below (same url, so SWR makes one
  // request). The tab count is the device's shot count: the listing's would be
  // its page length, which reads 100 for a device holding thousands.
  const { data: shotProperties } = useSWR<AvailableProperties>(
    deviceName ? shotPropertiesUrl(deviceName) : null,
    fetcher
  );

  const { data: datasets, error: datasetsError, isLoading: datasetsLoading } = useSWR<Dataset[]>(
    deviceName ? `${API_BASE}/devices/${deviceName}/datasets?scope=device` : null,
    fetcher
  );

  const jsonLd = <JsonLdPanel url={`${API_BASE}/devices/${deviceName}`} />;

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
          count={shotProperties?.total}
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

      {activeTab === 'shots' && <ShotList deviceName={deviceName} aside={jsonLd} />}

      {activeTab === 'shot-datasets' && (
        <ShotDatasets deviceName={deviceName} aside={jsonLd} />
      )}

      {/* Device Datasets Tab: no filters, so no side column to hold the JSON-LD. */}
      {activeTab === 'datasets' && (
        <div>
          <div className="mb-8">{jsonLd}</div>
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
