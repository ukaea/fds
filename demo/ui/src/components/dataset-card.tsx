'use client';

import Link from 'next/link';
import { Database, FileCode } from 'lucide-react';
import { Dataset } from '@/lib/types';
import { AnnotationBadges } from '@/components/features';

const BADGE = 'text-xs px-2 py-0.5 bg-muted text-foreground rounded-full border border-border';

// Friendly file-format label. Matched on substring rather than by table so that
// the compound types (application/vnd.icechunk+zarr) land in the right bucket.
export function formatMediaType(mediaType?: string): string {
  if (!mediaType) return 'Dataset';
  if (mediaType.includes('zarr')) return 'Zarr';
  if (mediaType.includes('netcdf')) return 'NetCDF';
  if (mediaType.includes('hdf')) return 'HDF5';
  return mediaType.split('/').pop() || mediaType;
}

/**
 * Where a dataset lives in the hierarchy, which is also where it is reachable.
 * Derived from the dataset rather than passed in: a shot-level dataset is under
 * its shot, a device-level one under its device, and a global one has no page.
 */
export function datasetHref(dataset: Dataset): string | null {
  if (dataset.id == null || !dataset.device_name) return null;
  return dataset.shot_id
    ? `/devices/${dataset.device_name}/shots/${dataset.shot_id}/datasets/${dataset.id}`
    : `/devices/${dataset.device_name}/datasets/${dataset.id}`;
}

/**
 * The dataset card, everywhere one is listed.
 *
 * Every badge is driven by what the dataset carries, so the same component reads
 * correctly in a shot's collection, a device's reference data and a flat filter
 * result. The one thing a caller decides is `showContext`: which device and shot
 * a dataset belongs to is worth saying in a listing that spans them, and noise
 * on a page that is already scoped to one.
 */
export function DatasetCard({
  dataset,
  showContext = false,
}: {
  dataset: Dataset;
  showContext?: boolean;
}) {
  const href = datasetHref(dataset);
  const subtitle = dataset.title || dataset.url;
  // Public is the default and labelling every card with it says nothing. Shown
  // only when access is restricted, where it is the thing you need to notice.
  const access = dataset.effective_access_level || dataset.access_level;
  const restricted = access && access !== 'public';

  const content = (
    <>
      <div className="flex items-start gap-3">
        <div className="bg-muted p-2 rounded text-foreground">
          <Database className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <h3 className="font-bold text-lg text-foreground">{dataset.name}</h3>
          {subtitle && (
            <p
              className={`text-muted-foreground mt-0.5 ${
                dataset.title ? 'text-sm' : 'text-xs font-mono break-all'
              }`}
            >
              {subtitle}
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3 text-sm text-muted-foreground flex-wrap">
        <div className="flex items-center gap-1">
          <FileCode className="w-4 h-4" />
          {formatMediaType(dataset.media_type)}
        </div>
        {showContext && dataset.device_name && (
          <span className={BADGE}>{dataset.device_name}</span>
        )}
        {showContext && (
          <span className={BADGE}>
            {dataset.shot_id ? `shot ${dataset.shot_id}` : 'device level'}
          </span>
        )}
        {restricted && <span className={BADGE}>{access}</span>}
        {dataset.level !== undefined && <span className={BADGE}>Level {dataset.level}</span>}
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

      {dataset.scientific_metadata && (
        <div className="mt-3">
          <AnnotationBadges properties={dataset.scientific_metadata} />
        </div>
      )}
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
