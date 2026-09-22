'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { Database, ChevronRight, MapPin, SlidersHorizontal, Copy, Check, Highlighter } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset } from '@/lib/types';
import { useDeviceLabel } from '@/lib/use-device-label';
import { coverageSummary } from '@/lib/coverage';
import { ScientificMetadata } from '@/components/features';
import { RelatedGroup } from '@/components/related-data';

function readSnippet(dataset?: Dataset): string {
  if (!dataset?.url) return '';
  return `import xarray as xr

ds = xr.open_dataset(
    "${dataset.url}",
    engine="h5netcdf",
    storage_options={"anon": True, "client_kwargs": {"endpoint_url": "http://localhost:9000"}},
)
print(ds)`;
}

function Property({
  label,
  value,
  mono,
  capitalize,
}: {
  label: string;
  value?: string;
  mono?: boolean;
  capitalize?: boolean;
}) {
  return (
    <div className="flex flex-col justify-start py-1 border-b border-border pb-2 last:border-b-0">
      <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">{label}</span>
      <span
        className={`text-foreground ${mono ? 'font-mono break-all text-xs' : ''} ${
          capitalize ? 'capitalize' : ''
        }`}
      >
        {value || 'Unknown'}
      </span>
    </div>
  );
}

export default function DeviceDatasetPage() {
  const params = useParams();
  const device = params.device as string;
  const deviceLabel = useDeviceLabel(device);
  const id = params.id as string;
  const [copied, setCopied] = useState(false);

  const { data: dataset, error, isLoading } = useSWR<Dataset>(
    id ? `${API_BASE}/datasets/id/${id}?include_annotations=true` : null,
    fetcher
  );

  const coverage = coverageSummary(dataset?.applies_to);
  const snippet = readSnippet(dataset);
  const isGeometry = Boolean(dataset?.geometry_roles?.length);
  const isCalibration = Boolean(dataset?.calibration_roles?.length);

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Breadcrumb */}
      <div className="flex items-center text-sm text-muted-foreground mb-6 font-medium">
        <Link href="/devices" className="hover:text-primary transition-colors">Devices</Link>
        <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
        <Link href={`/devices/${device}`} className="hover:text-primary transition-colors">{deviceLabel}</Link>
        <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
        <span className="text-foreground">{dataset?.name || id}</span>
      </div>

      {isLoading && <div className="text-muted-foreground py-8">Loading dataset…</div>}
      {error && <div className="text-destructive py-8">Failed to load dataset.</div>}

      {dataset && (
        <>
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold flex items-center gap-3 mb-4">
              <Database className="text-primary w-8 h-8" />
              {dataset.name}
            </h1>
            {dataset.description && (
              <p className="text-lg text-foreground max-w-4xl leading-relaxed mb-6">{dataset.description}</p>
            )}
            <div className="flex flex-wrap gap-3">
              <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">
                Device: {deviceLabel}
              </span>
              {dataset.geometry_roles?.map((role) => (
                <span
                  key={role}
                  className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border flex items-center gap-1"
                >
                  <MapPin className="w-3.5 h-3.5" />
                  {role}
                </span>
              ))}
              {dataset.calibration_roles?.map((role) => (
                <span
                  key={role}
                  className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border flex items-center gap-1"
                >
                  <SlidersHorizontal className="w-3.5 h-3.5" />
                  {role}
                  {dataset.calibration_stage != null && ` · stage ${dataset.calibration_stage}`}
                </span>
              ))}
              {dataset.annotates && (
                <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border flex items-center gap-1">
                  <Highlighter className="w-3.5 h-3.5" />
                  annotates {dataset.annotates}
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Properties */}
            <div className="card p-6">
              <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground">Dataset Properties</h3>
              <div className="space-y-3 text-sm">
                <Property label="URL" value={dataset.url} mono />
                <Property label="Media Type" value={dataset.media_type} />
                <Property
                  label="Access Level"
                  value={dataset.effective_access_level || dataset.access_level || 'unknown'}
                  capitalize
                />
                <Property
                  label="Created At"
                  value={
                    dataset.created_at
                      ? new Date(dataset.created_at).toLocaleDateString(undefined, {
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                        })
                      : 'Unknown'
                  }
                />
              </div>
            </div>

            {/* Reference version summary (geometry or calibration) */}
            {(isGeometry || isCalibration) && (
              <div className="card p-6">
                <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
                  {isGeometry ? (
                    <MapPin className="w-5 h-5 text-muted-foreground" />
                  ) : (
                    <SlidersHorizontal className="w-5 h-5 text-muted-foreground" />
                  )}
                  {isGeometry ? 'Geometry' : 'Calibration'}
                </h3>
                <div className="space-y-3 text-sm">
                  <div className="flex flex-col">
                    <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">
                      Provides
                    </span>
                    <span className="text-foreground">
                      {(isGeometry ? dataset.geometry_roles : dataset.calibration_roles)?.join(', ')}
                      {isCalibration &&
                        dataset.calibration_stage != null &&
                        ` · stage ${dataset.calibration_stage}`}
                    </span>
                  </div>
                  {coverage && (
                    <div className="flex flex-col">
                      <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">
                        Coverage
                      </span>
                      <span className="text-foreground font-mono text-xs">{coverage}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            <ScientificMetadata properties={dataset.scientific_metadata} />

            {(dataset.annotations?.length ?? 0) > 0 && (
              <div className="card p-6">
                <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground">Related Data</h3>
                <div className="text-sm">
                  <RelatedGroup
                    icon={Highlighter}
                    label="Annotations"
                    hint="— on this dataset's axes"
                    datasets={dataset.annotations}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Read snippet */}
          {snippet && (
            <div className="card p-6 mt-6">
              <div className="flex items-center justify-between mb-4 border-b border-border pb-2">
                <h3 className="text-lg font-bold text-foreground">Read with xarray</h3>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(snippet);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="text-xs bg-muted hover:bg-accent text-foreground px-3 py-1 rounded flex items-center gap-1 transition-colors"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5" /> Copied
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" /> Copy
                    </>
                  )}
                </button>
              </div>
              <pre className="text-foreground text-sm font-mono whitespace-pre-wrap bg-background border border-border p-4 rounded overflow-x-auto">
                {snippet}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}
