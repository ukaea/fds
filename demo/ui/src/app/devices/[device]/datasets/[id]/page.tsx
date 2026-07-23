'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { Database, ChevronRight, MapPin, Copy, Check } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, ReferenceCoverage } from '@/lib/types';

function coverageLines(coverage?: ReferenceCoverage): string[] {
  if (!coverage) return [];
  const lines: string[] = [];
  if (coverage.shots?.length) lines.push(`Shots: ${coverage.shots.join(', ')}`);
  coverage.shot_ranges?.forEach((range) =>
    lines.push(`Shot range: ${range.from_shot} → ${range.to_shot ?? 'open-ended'}`)
  );
  coverage.date_ranges?.forEach((range) =>
    lines.push(`Date range: ${range.from_date} → ${range.to_date ?? 'open-ended'}`)
  );
  return lines;
}

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
  const id = params.id as string;
  const [copied, setCopied] = useState(false);

  const { data: dataset, error, isLoading } = useSWR<Dataset>(
    id ? `${API_BASE}/datasets/id/${id}` : null,
    fetcher
  );

  const coverage = coverageLines(dataset?.applies_to);
  const snippet = readSnippet(dataset);
  const hasGeometry = Boolean(dataset?.geometry_roles?.length) || coverage.length > 0;

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Breadcrumb */}
      <div className="flex items-center text-sm text-muted-foreground mb-6 font-medium">
        <Link href="/devices" className="hover:text-primary transition-colors">Devices</Link>
        <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
        <Link href={`/devices/${device}`} className="hover:text-primary transition-colors">{device}</Link>
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
                Device: {device}
              </span>
              <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border">
                Device-level
              </span>
              {dataset.level !== undefined && (
                <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border">
                  Level {dataset.level}
                </span>
              )}
              {dataset.geometry_roles?.map((role) => (
                <span
                  key={role}
                  className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border flex items-center gap-1"
                >
                  <MapPin className="w-3.5 h-3.5" />
                  {role}
                </span>
              ))}
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
                  label="Processing Level"
                  value={dataset.level !== undefined ? `Level ${dataset.level}` : 'Unknown'}
                />
                <Property
                  label="Access Policy"
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

            {/* Reference geometry */}
            {hasGeometry && (
              <div className="card p-6">
                <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
                  <MapPin className="w-5 h-5 text-muted-foreground" /> Reference Geometry
                </h3>
                <div className="space-y-3 text-sm">
                  {dataset.geometry_roles?.length ? (
                    <div className="flex flex-col">
                      <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">
                        Provides roles
                      </span>
                      <span className="text-foreground">{dataset.geometry_roles.join(', ')}</span>
                    </div>
                  ) : null}
                  {coverage.length > 0 && (
                    <div className="flex flex-col">
                      <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">
                        Applies to
                      </span>
                      <ul className="text-foreground list-disc list-inside space-y-1">
                        {coverage.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    </div>
                  )}
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
