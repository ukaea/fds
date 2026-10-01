'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { AvailableProperties, Shot } from '@/lib/types';
import { propertyQuery, withQuery } from '@/lib/properties';
import { PropertyFilter } from '@/components/property-filter';
import { PropertyBadges } from '@/components/properties';
import { ClientDate } from '@/components/client-date';

const PAGE_SIZE = 100;

export function shotsUrl(deviceName: string): string {
  return `${API_BASE}/devices/${deviceName}/shots/`;
}

// No trailing slash: the listing's costs a 307 through the proxy, and this url
// is shared as an SWR key by three components, so it is worth getting right.
export function shotPropertiesUrl(deviceName: string): string {
  return `${API_BASE}/devices/${deviceName}/shots/properties`;
}

// Values of one name, searched server-side: a device's `objective` runs to
// hundreds of values several hundred characters long.
export function shotPropertyValuesUrl(deviceName: string) {
  return (name: string, query: string) =>
    withQuery(
      `${API_BASE}/devices/${deviceName}/shots/properties/${encodeURIComponent(name)}/values`,
      query ? `q=${encodeURIComponent(query)}` : ''
    );
}

type Range = { min?: number; max?: number };

// `property_min=name:number`, one parameter per bound, skipping bounds the
// user has not set.
function rangeQuery(ranges: Record<string, Range>): string {
  const parts: string[] = [];
  for (const [name, range] of Object.entries(ranges)) {
    if (range.min !== undefined)
      parts.push(`property_min=${encodeURIComponent(`${name}:${range.min}`)}`);
    if (range.max !== undefined)
      parts.push(`property_max=${encodeURIComponent(`${name}:${range.max}`)}`);
  }
  return parts.join('&');
}

/**
 * A device's shots, narrowable by the properties its shots carry.
 *
 * The chips and the counts come from the properties endpoint, which aggregates over
 * the whole device rather than over a page. That matters at real scale: a
 * 5,300-shot device's properties cannot be inferred from the hundred shots a
 * page happens to hold, and its shot count is not the length of that page.
 */
export function ShotList({ deviceName }: { deviceName: string }) {
  const [propertyTokens, selectProperties] = useState<string[]>([]);
  const [ranges, boundRanges] = useState<Record<string, Range>>({});
  const [page, setPage] = useState(0);

  // Narrowing the filter can leave the current page past the end of the
  // results, so changing it returns to the first. Done here rather than in an
  // effect: an effect would set state after the render that caused it, which
  // costs a second render for every keystroke on a filter.
  const setPropertyTokens = (next: string[]) => {
    selectProperties(next);
    setPage(0);
  };
  const setRanges = (next: Record<string, Range>) => {
    boundRanges(next);
    setPage(0);
  };

  // Unfiltered: the chips are the control you are using, so they must not
  // rearrange themselves as you narrow. Shared as an SWR key with DeviceDetail
  // and ShotDatasets, so the three of them make one request.
  const { data: properties } = useSWR<AvailableProperties>(
    deviceName ? shotPropertiesUrl(deviceName) : null,
    fetcher
  );

  // Filtered: an exact count of the matches. The listing cannot give one, since
  // its page is capped well below the number of shots that may match.
  const filterQuery = [
    propertyQuery('property', propertyTokens),
    rangeQuery(ranges),
  ].filter(Boolean);

  const { data: matching } = useSWR<AvailableProperties>(
    deviceName && filterQuery.length > 0
      ? withQuery(shotPropertiesUrl(deviceName), ...filterQuery)
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  // keepPreviousData holds the current rows in place while the next page or
  // filter loads, so the list settles rather than blanking on every click.
  const { data: shots, error, isLoading } = useSWR<Shot[]>(
    deviceName
      ? withQuery(
          shotsUrl(deviceName),
          ...filterQuery,
          `offset=${page * PAGE_SIZE}`,
          `limit=${PAGE_SIZE}`
        )
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  const total = properties?.total ?? 0;
  const matched = filterQuery.length > 0 ? matching?.total ?? 0 : total;
  const pages = Math.max(1, Math.ceil(matched / PAGE_SIZE));

  return (
    <div>
      {/* Outside the loading branch below: the chips are the control you are
          using, so they must not vanish while the result of a click arrives. */}
      <PropertyFilter
        label="Filter by scientific metadata"
        properties={properties?.properties ?? []}
        selected={propertyTokens}
        onChange={setPropertyTokens}
        ranges={ranges}
        onRangesChange={setRanges}
        valuesUrl={shotPropertyValuesUrl(deviceName)}
      />

      {total > 0 && (
        <p className="text-sm text-muted-foreground mb-4">
          {filterQuery.length > 0
            ? `${matched} of ${total} shot${total !== 1 ? 's' : ''}`
            : `${total} shot${total !== 1 ? 's' : ''}`}
          {pages > 1 && `, page ${page + 1} of ${pages}`}
        </p>
      )}

      {error && <div className="py-8 text-destructive">Failed to load shots.</div>}
      {isLoading && !shots && (
        <div className="py-8 text-muted-foreground">Loading shots...</div>
      )}

      <div className="space-y-4">
        {shots?.map((shot) => (
          <Link
            key={shot.id}
            href={`/devices/${deviceName}/shots/${shot.id}`}
            className="block card p-6 hover:bg-muted transition-colors group"
          >
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <span className="bg-muted text-foreground px-3 py-1 rounded-full text-xs font-mono font-bold">
                    #{shot.id}
                  </span>
                  {/* The shot's own description, when it has one. Every shot
                      previously claimed to be a "Standard Plasma Experiment",
                      which was asserted of the record rather than read from it. */}
                  {shot.description && (
                    <span className="text-foreground font-medium truncate">{shot.description}</span>
                  )}
                </div>
                <div className="flex items-center gap-4 text-sm text-muted-foreground mt-2">
                  <div className="flex items-center gap-1">
                    <Calendar className="w-4 h-4" />
                    <ClientDate timestamp={shot.timestamp} />
                  </div>
                </div>
                <div className="mt-3">
                  <PropertyBadges properties={shot.scientific_metadata} />
                </div>
              </div>
              <ChevronRight className="shrink-0 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
            </div>
          </Link>
        ))}

        {shots && shots.length === 0 && (
          <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
            {filterQuery.length > 0
              ? 'No shots match this filter.'
              : 'No shots found for this device.'}
          </div>
        )}
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-4 mt-6">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:hover:text-muted-foreground transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>
          <span className="text-sm text-muted-foreground tabular-nums">
            {page + 1} / {pages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
            disabled={page >= pages - 1}
            className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:hover:text-muted-foreground transition-colors"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
