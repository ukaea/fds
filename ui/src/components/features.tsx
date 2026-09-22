'use client';

import { Tag } from 'lucide-react';
import { ScientificProperty } from '@/lib/types';
import { extentSummary, formatValue, splitProperties } from '@/lib/features';

// One annotated feature: its name and value, plus where it sits on its axis.
function FeatureRow({ property }: { property: ScientificProperty }) {
  const extent = extentSummary(property.extent);
  const isPoint = property.extent?.end == null;
  return (
    <div className="bg-card border border-border rounded p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium text-foreground">{property.name}</span>
        <span className="text-sm text-foreground font-mono">
          {formatValue(property.value)}
          {property.unit ? ` ${property.unit}` : ''}
        </span>
      </div>
      {extent && (
        <p className="text-xs text-muted-foreground font-mono mt-1">
          {extent}
          <span className="ml-2 not-italic opacity-70">{isPoint ? '(point)' : '(span)'}</span>
        </p>
      )}
      {property.description && (
        <p className="text-xs text-muted-foreground mt-1">{property.description}</p>
      )}
    </div>
  );
}

// A property with no extent: a plain scalar, shown as a compact label/value line.
function PlainRow({ property }: { property: ScientificProperty }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1 border-b border-border last:border-b-0">
      <span className="text-muted-foreground">{property.name}</span>
      <span className="text-foreground font-mono text-xs">
        {formatValue(property.value)}
        {property.unit ? ` ${property.unit}` : ''}
      </span>
    </div>
  );
}

// The row-level treatment of the same annotations: name and value only, with the
// extent on hover. Keeps a list row readable where the card below would not fit.
export function AnnotationBadges({
  properties,
  limit = 4,
}: {
  properties?: ScientificProperty[];
  limit?: number;
}) {
  const all = properties ?? [];
  if (all.length === 0) return null;
  const shown = all.slice(0, limit);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {shown.map((property, i) => (
        <span
          key={`${property.name}-${i}`}
          title={extentSummary(property.extent) ?? undefined}
          className="text-xs px-2 py-0.5 bg-muted text-foreground rounded-full border border-border"
        >
          {property.name}
          {property.value != null && (
            <span className="ml-1 font-mono text-muted-foreground">
              {formatValue(property.value)}
            </span>
          )}
        </span>
      ))}
      {all.length > shown.length && (
        <span className="text-xs text-muted-foreground">+{all.length - shown.length}</span>
      )}
    </div>
  );
}

// Renders a scientific_metadata list, separating the features (localised on an
// axis) from the plain properties. Renders nothing when there is nothing to show.
export function ScientificMetadata({
  properties,
  className = '',
}: {
  properties?: ScientificProperty[];
  className?: string;
}) {
  const { features, plain } = splitProperties(properties);
  if (features.length === 0 && plain.length === 0) return null;

  return (
    <div className={`card p-6 ${className}`}>
      <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
        <Tag className="w-5 h-5 text-muted-foreground" />
        {features.length > 0 ? 'Features' : 'Scientific Metadata'}
      </h3>
      {features.length > 0 && (
        <div className="space-y-2">
          {features.map((property, i) => (
            <FeatureRow key={`${property.name}-${i}`} property={property} />
          ))}
        </div>
      )}
      {plain.length > 0 && (
        <div className={`text-sm ${features.length > 0 ? 'mt-4 pt-3 border-t border-border' : ''}`}>
          {features.length > 0 && (
            <p className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-2">
              Other properties
            </p>
          )}
          {plain.map((property, i) => (
            <PlainRow key={`${property.name}-${i}`} property={property} />
          ))}
        </div>
      )}
      {features.length > 0 && (
        <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
          Each coordinate is on the named axis, in that axis&apos;s own frame. Aligning one to a
          particular diagnostic is the consumer&apos;s call.
        </p>
      )}
    </div>
  );
}
