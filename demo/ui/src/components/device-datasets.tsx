'use client';

import { Database, Ruler, SlidersHorizontal } from 'lucide-react';
import { ReactNode } from 'react';
import { Dataset } from '@/lib/types';
import { DatasetCard } from '@/components/dataset-card';

function Section({
  title,
  icon,
  datasets,
}: {
  title: string;
  icon: ReactNode;
  datasets: Dataset[];
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
          <DatasetCard key={d.id ?? d.name} dataset={d} />
        ))}
      </div>
    </div>
  );
}

/**
 * Renders a device's datasets, splitting the special reference kinds —
 * geometry and calibration versions — into their own sections above the rest.
 */
export function DeviceDatasets({ datasets }: { datasets: Dataset[] }) {
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
      />
      <Section
        title="Calibration"
        icon={<SlidersHorizontal className="w-4 h-4 text-primary" />}
        datasets={calibration}
      />
      <Section
        title={hasReference ? 'Other Datasets' : 'Datasets'}
        icon={<Database className="w-4 h-4 text-muted-foreground" />}
        datasets={other}
      />
    </div>
  );
}
