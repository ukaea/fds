'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Dataset, Collection, Activity, Source, Shot } from '@/lib/types';
import { useDeviceLabel } from '@/lib/use-device-label';
import { Database, ChevronRight, Layers, MapPin, SlidersHorizontal, Highlighter } from 'lucide-react';
import { annotationFacets, annotationQuery, withQuery } from '@/lib/features';
import { dedupeById } from '@/components/resolved-ref';
import { AnnotationFilter } from '@/components/annotation-filter';
import { DatasetCard } from '@/components/dataset-card';
import { DatasetResults } from '@/components/dataset-results';
import { AnnotationBadges, ScientificMetadata } from '@/components/features';
import { RelatedGroup } from '@/components/related-data';

function formatSourceName(name: string): string {
  return name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function formatDate(iso?: string): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function CollectionSection({
  collection,
  sourcesById,
}: {
  collection: Collection;
  sourcesById: Map<number, string>;
}) {
  const { data: activity } = useSWR<Activity>(
    collection.activity_id ? `${API_BASE}/activities/${collection.activity_id}` : null,
    fetcher
  );

  const sourceName = activity?.source_id != null ? sourcesById.get(activity.source_id) : undefined;
  let activityLabel: string | undefined;
  if (sourceName) {
    activityLabel = formatSourceName(sourceName);
    if (activity?.started_at) activityLabel += ` · ${formatDate(activity.started_at)}`;
  } else if (activity?.activity_type) {
    activityLabel = activity.activity_type;
    if (activity.started_at) activityLabel += ` · ${formatDate(activity.started_at)}`;
  }

  const datasetCount = collection.datasets?.length ?? 0;

  return (
    <div className="mb-10">
      <div className="flex items-center gap-3 mb-4">
        <div className="bg-muted p-2 rounded-lg text-foreground">
          <Layers className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground">{collection.title || collection.name}</h2>
          {activityLabel && (
            <p className="text-sm text-muted-foreground mt-0.5">{activityLabel}</p>
          )}
        </div>
        <span className="text-sm text-muted-foreground ml-1">
          ({datasetCount} dataset{datasetCount !== 1 ? 's' : ''})
        </span>
      </div>

      {/* The collection's own features, kept apart from the shot's above: a
          simulation may report H-mode on a shot that never reached it. */}
      {collection.scientific_metadata && collection.scientific_metadata.length > 0 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <span className="text-xs text-muted-foreground">Features:</span>
          <AnnotationBadges properties={collection.scientific_metadata} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {collection.datasets?.map((dataset) => (
          <DatasetCard key={dataset.id ?? dataset.name} dataset={dataset} />
        ))}
      </div>
    </div>
  );
}

export default function ShotDetailPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const deviceLabel = useDeviceLabel(deviceName);
  const shotId = params.shot as string;

  // The shot itself carries its features (inline scientific_metadata) and, with
  // include_annotations, the annotation datasets expressed in its own frame.
  const { data: shot } = useSWR<Shot>(
    deviceName && shotId
      ? `${API_BASE}/devices/${deviceName}/shots/${shotId}?include_annotations=true`
      : null,
    fetcher
  );

  const [annotations, setAnnotations] = useState<string[]>([]);

  const datasetsUrl =
    deviceName && shotId
      ? `${API_BASE}/devices/${deviceName}/shots/${shotId}/datasets?include_geometry=true&include_calibration=true`
      : null;

  const { data: datasets, error, isLoading } = useSWR<Dataset[]>(datasetsUrl, fetcher);

  // The shot's datasets narrowed to those carrying the selected annotations.
  const { data: matchingDatasets, isLoading: matchingLoading } = useSWR<Dataset[]>(
    datasetsUrl && annotations.length > 0
      ? withQuery(datasetsUrl, annotationQuery('annotation', annotations))
      : null,
    fetcher,
    { keepPreviousData: true }
  );

  const { data: collections } = useSWR<Collection[]>(
    deviceName && shotId ? `${API_BASE}/devices/${deviceName}/shots/${shotId}/collections` : null,
    fetcher
  );

  const { data: sources } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);

  const sourcesById = new Map<number, string>(sources?.map(s => [s.id, s.name]) ?? []);

  // Datasets already shown inside a collection
  const datasetIdsInCollections = new Set<number>(
    collections?.flatMap(col => col.datasets?.map(ds => ds.id).filter((id): id is number => id != null) ?? []) ?? []
  );
  // Annotation datasets are presented as the shot's annotations, not as another
  // diagnostic, so keep them out of the plain dataset grid.
  const uncollectedDatasets = datasets?.filter(
    ds => ds.id != null && !datasetIdsInCollections.has(ds.id!) && !ds.annotates
  ) ?? [];

  // Reference data resolved for this shot, aggregated across its datasets.
  const resolvedGeometry = dedupeById((datasets ?? []).flatMap(ds => ds.geometry ?? []));
  const resolvedCalibration = dedupeById((datasets ?? []).flatMap(ds => ds.calibration ?? [])).sort(
    (a, b) => (a.calibration_stage ?? 0) - (b.calibration_stage ?? 0)
  );

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center text-sm text-muted-foreground mb-2">
          <Link href={`/devices/${deviceName}`} className="hover:text-primary transition-colors">{deviceLabel}</Link>
          <ChevronRight className="w-4 h-4 mx-2" />
          <span className="text-foreground font-medium">Shot #{shotId}</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-2">Shot #{shotId}</h1>
        <p className="text-muted-foreground">{shot?.description || 'Scientific data and collections for this shot.'}</p>
        {shot?.t0_at && (
          <p className="text-sm text-muted-foreground mt-2">
            <span className="uppercase text-xs font-bold tracking-wider">t=0</span>{' '}
            <span className="font-mono">{formatDate(shot.t0_at)}</span>
            <span className="ml-2">— the shot&apos;s relative time base zero</span>
          </p>
        )}
      </div>

      {/* Features annotated on the shot record itself — metadata, not a dataset, so
          it sits with the shot rather than with the data resolved for it. */}
      <ScientificMetadata properties={shot?.scientific_metadata} className="mb-10" />

      {isLoading && (
        <div className="card p-6 text-center text-muted-foreground">Loading datasets…</div>
      )}
      {error && (
        <div className="card p-6 text-center text-destructive">Failed to load datasets.</div>
      )}

      {/* Annotations carried by this shot's datasets, describing the data itself
          rather than the plasma. Absent on most shots, in which case this and the
          filtered view below never appear. */}
      <AnnotationFilter
        label="Filter datasets by annotation"
        facets={annotationFacets(datasets)}
        selected={annotations}
        onChange={setAnnotations}
      />

      {/* Filtering answers with one flat list. The collections below group every
          dataset they hold, so a filtered count against them would not add up. */}
      {annotations.length > 0 && (
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-foreground">Matching Datasets</h2>
            <span className="text-sm text-muted-foreground">
              ({matchingDatasets?.length ?? 0} of {datasets?.length ?? 0})
            </span>
          </div>
          {matchingLoading && !matchingDatasets ? (
            <div className="card p-6 text-center text-muted-foreground">Loading datasets…</div>
          ) : (
            <DatasetResults
              datasets={matchingDatasets}
              emptyMessage="No datasets in this shot carry every selected annotation."
            />
          )}
        </div>
      )}

      {/* One section per collection */}
      {annotations.length === 0 &&
        collections?.map((collection) => (
          <CollectionSection
            key={collection.id}
            collection={collection}
            sourcesById={sourcesById}
          />
        ))}

      {/* Datasets not in any collection */}
      {annotations.length === 0 && uncollectedDatasets.length > 0 && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-foreground">Other Datasets</h2>
            <span className="text-sm text-muted-foreground">({uncollectedDatasets.length})</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {uncollectedDatasets.map((dataset) => (
              <DatasetCard key={dataset.id ?? dataset.name} dataset={dataset} />
            ))}
          </div>
        </div>
      )}

      {/* Datasets resolved for this shot: the reference versions its data reads
          against, and the annotations localising its features. */}
      {(resolvedGeometry.length > 0 || resolvedCalibration.length > 0 || (shot?.annotations?.length ?? 0) > 0) && (
        <div className="mt-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Database className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-semibold text-foreground">Related Data</h2>
            <span className="text-sm text-muted-foreground">resolved for this shot</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <RelatedGroup icon={MapPin} label="Geometry" datasets={resolvedGeometry} />
            <RelatedGroup
              icon={SlidersHorizontal}
              label="Calibration"
              hint="— applied in order"
              datasets={resolvedCalibration}
            />
            <RelatedGroup
              icon={Highlighter}
              label="Annotations"
              hint="— on this shot's axes"
              datasets={shot?.annotations}
            />
          </div>
        </div>
      )}

      {!isLoading && !error && datasets?.length === 0 && (
        <div className="py-12 text-center text-muted-foreground border border-dashed border-border rounded-lg">
          No datasets found for this shot.
        </div>
      )}
    </div>
  );
}
