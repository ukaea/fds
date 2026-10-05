'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Calendar, ChevronRight, Search } from 'lucide-react';
import { fetcher, API_BASE, FetchError } from '@/lib/api';
import { AvailableProperties, Shot } from '@/lib/types';
import { propertyQuery, withQuery } from '@/lib/properties';
import { usePagedList } from '@/lib/use-paged-list';
import { PropertyFilter } from '@/components/property-filter';
import { SidePanelLayout } from '@/components/side-panel-layout';
import { LoadMore } from '@/components/load-more';
import { PropertyBadges } from '@/components/properties';
import { ClientDate } from '@/components/client-date';

const PAGE_SIZE = 100;

function shotUrl(deviceName: string, shotId: string): string {
  return `${API_BASE}/devices/${deviceName}/shots/${encodeURIComponent(shotId)}`;
}

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
export function ShotList({
  deviceName,
  aside,
}: {
  deviceName: string;
  // Shown under the filters, e.g. the device's JSON-LD.
  aside?: React.ReactNode;
}) {
  const [propertyTokens, setPropertyTokens] = useState<string[]>([]);
  const [ranges, setRanges] = useState<Record<string, Range>>({});
  const [idPrefix, setIdPrefix] = useState('');
  const [notFound, setNotFound] = useState<string | null>(null);
  const router = useRouter();

  // Enter goes straight to the shot typed. Only a missing shot keeps you here,
  // so a typo reports itself beside the box; the shot page explains the rest.
  async function goToShot(e: React.FormEvent) {
    e.preventDefault();
    const shotId = idPrefix.trim();
    if (!shotId) return;
    try {
      await fetcher(shotUrl(deviceName, shotId));
    } catch (err) {
      if (err instanceof FetchError && err.status === 404) {
        setNotFound(shotId);
        return;
      }
    }
    router.push(`/devices/${deviceName}/shots/${encodeURIComponent(shotId)}`);
  }

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
    idPrefix.trim() ? `id_prefix=${encodeURIComponent(idPrefix.trim())}` : '',
  ].filter(Boolean);

  const { data: matching } = useSWR<AvailableProperties>(
    deviceName && filterQuery.length > 0
      ? withQuery(shotPropertiesUrl(deviceName), ...filterQuery)
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  const {
    items: shots,
    error,
    isLoading,
    done,
    loadingMore,
    loadMore,
  } = usePagedList<Shot>(
    deviceName ? withQuery(shotsUrl(deviceName), ...filterQuery) : null,
    PAGE_SIZE
  );

  const total = properties?.total ?? 0;
  const matched = filterQuery.length > 0 ? matching?.total ?? 0 : total;

  return (
    <SidePanelLayout
      side={
        (!!properties?.properties.length || aside) && (
          <>
            {/* Outside the loading branch below: the chips are the control you
                are using, so they must not vanish while a click's result arrives. */}
            {!!properties?.properties.length && (
              <PropertyFilter
                properties={properties.properties}
                selected={propertyTokens}
                onChange={setPropertyTokens}
                ranges={ranges}
                onRangesChange={setRanges}
                valuesUrl={shotPropertyValuesUrl(deviceName)}
              />
            )}
            {aside}
          </>
        )
      }
    >
      <form onSubmit={goToShot} className="mb-4">
        <div className="relative w-full md:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="search"
            value={idPrefix}
            onChange={(e) => {
              setIdPrefix(e.target.value);
              setNotFound(null);
            }}
            placeholder="Find a shot by ID"
            aria-label="Find a shot by ID"
            className="w-full pl-9 pr-3 py-2 text-sm bg-card border border-border rounded-lg text-foreground placeholder-muted-foreground focus:outline-none focus:border-foreground/40"
          />
        </div>
        {notFound && (
          <p role="alert" className="text-sm text-destructive mt-2">
            No shot {notFound} on this device.
          </p>
        )}
      </form>

      {total > 0 && (
        <p className="text-sm text-muted-foreground mb-4">
          {filterQuery.length > 0
            ? `${matched} of ${total} shot${total !== 1 ? 's' : ''}`
            : `${total} shot${total !== 1 ? 's' : ''}`}
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
                    <ClientDate timestamp={shot.shot_at} />
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

      {shots && shots.length > 0 && (
        <LoadMore onLoad={loadMore} loading={loadingMore} done={done} />
      )}
    </SidePanelLayout>
  );
}
