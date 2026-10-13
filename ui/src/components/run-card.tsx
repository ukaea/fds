'use client';

import Link from 'next/link';
import { Database, Layers } from 'lucide-react';
import { Collection } from '@/lib/types';
import { useDeviceLabel } from '@/lib/use-device-label';
import { PropertyBadges } from '@/components/properties';
import { RunBadge } from '@/components/run-label';

const BADGE = 'text-xs px-2 py-0.5 bg-muted text-foreground rounded-full border border-border';

// A collection read inlines at most this many of each kind of member.
const INLINE_MEMBERS = 100;

export function memberCount(count: number, noun: string): string {
  const shown = count >= INLINE_MEMBERS ? `${INLINE_MEMBERS}+` : `${count}`;
  return `${shown} ${noun}${count === 1 ? '' : 's'}`;
}

/**
 * Where a collection sits, in words: on a shot, on a device as a whole, or on
 * neither. A run that modelled no shot, such as a predictive scenario, is a
 * device-level collection, and saying so is how a reader tells it from a
 * reconstruction of a real discharge.
 */
export function CollectionPlace({ collection }: { collection: Collection }) {
  const deviceLabel = useDeviceLabel(collection.device_name ?? undefined);
  if (!collection.device_name) return <span className={BADGE}>not tied to a device</span>;
  return (
    <span className={BADGE}>
      {deviceLabel}
      {collection.shot_id ? ` · shot ${collection.shot_id}` : ' · no shot'}
    </span>
  );
}

/**
 * A run's bundle as a list row: what ran, where, what the run says it was
 * about, and how much it produced. Links to the collection, the run's citable
 * record.
 */
export function RunCard({ collection }: { collection: Collection }) {
  const members = collection.datasets?.length ?? 0;

  return (
    <Link
      href={`/collections/${collection.id}`}
      className="card p-5 block hover:border-primary/50 transition-colors"
    >
      <div className="flex items-start gap-3">
        <div className="bg-muted p-2 rounded-lg text-foreground">
          <Layers className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <h3 className="font-semibold text-foreground">{collection.title || collection.name}</h3>
          {collection.title && (
            <p className="text-xs text-muted-foreground font-mono mt-0.5">{collection.name}</p>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
        <RunBadge activity={collection.activity} />
        <CollectionPlace collection={collection} />
        {members > 0 && (
          <span className="flex items-center gap-1">
            <Database className="w-3.5 h-3.5" />
            {memberCount(members, 'dataset')}
          </span>
        )}
      </div>

      {!!collection.scientific_metadata?.length && (
        <div className="mt-3">
          <PropertyBadges properties={collection.scientific_metadata} />
        </div>
      )}
    </Link>
  );
}
