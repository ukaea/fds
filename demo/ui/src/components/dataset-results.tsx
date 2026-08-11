'use client';

import { Dataset } from '@/lib/types';
import { DatasetCard } from '@/components/dataset-card';

/**
 * A flat list of datasets, for the views that are answering a query rather than
 * browsing a hierarchy. Results can span devices and shots, so each card carries
 * the context a nested listing would have supplied.
 */
export function DatasetResults({
  datasets,
  emptyMessage = 'No datasets match.',
}: {
  datasets?: Dataset[];
  emptyMessage?: string;
}) {
  if (!datasets || datasets.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
        {emptyMessage}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {datasets.map((dataset) => (
        <DatasetCard key={dataset.id ?? dataset.name} dataset={dataset} showContext />
      ))}
    </div>
  );
}
