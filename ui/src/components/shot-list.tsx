'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Calendar, ChevronRight } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Shot } from '@/lib/types';
import { annotationFacets, annotationQuery, withQuery } from '@/lib/features';
import { AnnotationFilter } from '@/components/annotation-filter';
import { AnnotationBadges } from '@/components/features';
import { ClientDate } from '@/components/client-date';

export function shotsUrl(deviceName: string): string {
  return `${API_BASE}/devices/${deviceName}/shots/`;
}

/**
 * A device's shots, narrowable by the annotations its shots carry.
 *
 * Two requests, not one: the chips come from the unfiltered listing so they stay
 * put as you narrow, and the rows from the filtered one. With nothing selected
 * the two urls are identical and SWR makes the single request.
 */
export function ShotList({ deviceName }: { deviceName: string }) {
  const [annotations, setAnnotations] = useState<string[]>([]);

  const { data: allShots } = useSWR<Shot[]>(deviceName ? shotsUrl(deviceName) : null, fetcher);

  // keepPreviousData holds the current rows in place while the next filter
  // loads, so the list settles rather than blanking on every chip.
  const { data: shots, error, isLoading } = useSWR<Shot[]>(
    deviceName
      ? withQuery(shotsUrl(deviceName), annotationQuery('annotation', annotations))
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  const total = allShots?.length ?? 0;
  const matched = shots?.length ?? 0;

  return (
    <div>
      {/* Outside the loading branch below: the chips are the control you are
          using, so they must not vanish while the result of a click arrives. */}
      <AnnotationFilter
        label="Filter by annotation"
        facets={annotationFacets(allShots)}
        selected={annotations}
        onChange={setAnnotations}
      />

      {annotations.length > 0 && (
        <p className="text-sm text-muted-foreground mb-4">
          {matched} of {total} shot{total !== 1 ? 's' : ''}
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
                  <AnnotationBadges properties={shot.scientific_metadata} />
                </div>
              </div>
              <ChevronRight className="shrink-0 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
            </div>
          </Link>
        ))}

        {shots && matched === 0 && (
          <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
            {annotations.length > 0
              ? 'No shots carry every selected annotation.'
              : 'No shots found for this device.'}
          </div>
        )}
      </div>
    </div>
  );
}
