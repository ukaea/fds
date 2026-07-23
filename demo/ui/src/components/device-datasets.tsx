'use client';

import Link from 'next/link';
import { Database, FileCode, Ruler, SlidersHorizontal } from 'lucide-react';
import { ReactNode } from 'react';
import { Dataset } from '@/lib/types';

const BADGE = 'text-xs px-2 py-0.5 bg-muted text-foreground rounded-full border border-border';

// Friendly file-format label for a media type (e.g. application/x-netcdf → NetCDF).
const FORMAT_LABELS: Record<string, string> = {
  'application/x-netcdf': 'NetCDF',
  'application/x-zarr': 'Zarr',
  'application/x-hdf5': 'HDF5',
};

function formatLabel(mediaType?: string): string {
  if (!mediaType) return 'Dataset';
  return FORMAT_LABELS[mediaType] ?? mediaType;
}

function DatasetCard({ dataset, deviceName }: { dataset: Dataset; deviceName: string }) {
  const href = dataset.id ? `/devices/${deviceName}/datasets/${dataset.id}` : undefined;
  const content = (
    <>
      <div className="flex items-center gap-3">
        <div className="bg-muted p-2 rounded text-foreground">
          <Database className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <h3 className="font-bold text-lg text-foreground">{dataset.name}</h3>
          {dataset.url && (
            <p className="text-xs text-muted-foreground font-mono mt-1 break-all">{dataset.url}</p>
          )}
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3 text-sm text-muted-foreground flex-wrap">
        <div className="flex items-center gap-1">
          <FileCode className="w-4 h-4" />
          {formatLabel(dataset.media_type)}
        </div>
        {!!dataset.geometry_roles?.length && (
          <span className={BADGE}>geometry: {dataset.geometry_roles.join(', ')}</span>
        )}
        {!!dataset.calibration_roles?.length && (
          <span className={BADGE}>
            calibration: {dataset.calibration_roles.join(', ')}
            {dataset.calibration_stage != null && ` · stage ${dataset.calibration_stage}`}
          </span>
        )}
      </div>
    </>
  );
  return href ? (
    <Link href={href} className="card p-6 block hover:border-primary/50 transition-colors">
      {content}
    </Link>
  ) : (
    <div className="card p-6">{content}</div>
  );
}

function Section({
  title,
  icon,
  datasets,
  deviceName,
}: {
  title: string;
  icon: ReactNode;
  datasets: Dataset[];
  deviceName: string;
}) {
  if (datasets.length === 0) return null;
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h3 className="text-sm font-semibold text-foreground uppercase tracking-wide">{title}</h3>
        <span className="text-xs text-muted-foreground">({datasets.length})</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datasets.map((d) => (
          <DatasetCard key={d.id ?? d.name} dataset={d} deviceName={deviceName} />
        ))}
      </div>
    </div>
  );
}

/**
 * Renders a device's datasets, splitting the special reference kinds —
 * geometry and calibration versions — into their own sections above the rest.
 */
export function DeviceDatasets({
  datasets,
  deviceName,
}: {
  datasets: Dataset[];
  deviceName: string;
}) {
  const geometry = datasets.filter((d) => d.geometry_roles?.length);
  const calibration = datasets.filter((d) => d.calibration_roles?.length);
  const other = datasets.filter(
    (d) => !d.geometry_roles?.length && !d.calibration_roles?.length
  );
  const hasReference = geometry.length > 0 || calibration.length > 0;

  return (
    <div>
      <Section
        title="Geometry"
        icon={<Ruler className="w-4 h-4 text-primary" />}
        datasets={geometry}
        deviceName={deviceName}
      />
      <Section
        title="Calibration"
        icon={<SlidersHorizontal className="w-4 h-4 text-primary" />}
        datasets={calibration}
        deviceName={deviceName}
      />
      <Section
        title={hasReference ? 'Other Datasets' : 'Datasets'}
        icon={<Database className="w-4 h-4 text-muted-foreground" />}
        datasets={other}
        deviceName={deviceName}
      />
    </div>
  );
}
