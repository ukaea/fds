'use client';

import { Tag } from 'lucide-react';
import { ScientificProperty } from '@/lib/types';
import {
  extentSummary,
  formatValue,
  isGroup,
  propertySummary,
  splitProperties,
  valuedProperties,
} from '@/lib/properties';
import { DescribedName } from '@/components/described-name';

// One annotation: its name and value, plus where it sits on its axis. A value
// of `true` only says the feature is present, which the row already says. An
// annotated group lists what it holds below, all of it covered by its extent.
function AnnotationRow({ property }: { property: ScientificProperty }) {
  const extent = extentSummary(property.extent);
  const group = isGroup(property);
  return (
    <div className="bg-card border border-border rounded-sm p-3">
      <div className="flex items-baseline justify-between gap-2">
        <DescribedName
          name={property.name}
          description={property.description}
          className="font-medium text-foreground"
        />
        {!group && property.value !== true && (
          <span className="text-sm text-foreground font-mono">
            {formatValue(property.value)}
            {property.unit ? ` ${property.unit}` : ''}
          </span>
        )}
      </div>
      {extent && <p className="text-xs text-muted-foreground font-mono mt-1">{extent}</p>}
      {group && (
        <div className="text-sm mt-2">
          <PropertyRows properties={property.properties} />
        </div>
      )}
    </div>
  );
}

// A group: its name, then what it holds, indented under a rule so the rows
// inside read as belonging to it. A group inside a group nests the same way.
function GroupSection({ property }: { property: ScientificProperty }) {
  return (
    <div className="py-1 border-b border-border last:border-b-0">
      <DescribedName
        name={property.name}
        description={property.description}
        className="text-muted-foreground"
      />
      <div className="mt-1 ml-1 pl-3 border-l border-border">
        <PropertyRows properties={property.properties} />
      </div>
    </div>
  );
}

function PropertyRows({ properties }: { properties?: ScientificProperty[] | null }) {
  return (
    <>
      {(properties ?? []).map((property, i) =>
        isGroup(property) ? (
          <GroupSection key={`${property.name}-${i}`} property={property} />
        ) : (
          <PlainRow key={`${property.name}-${i}`} property={property} />
        )
      )}
    </>
  );
}

// A property with no extent and a value, shown as a compact label/value line.
function PlainRow({ property }: { property: ScientificProperty }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1 border-b border-border last:border-b-0">
      <DescribedName
        name={property.name}
        description={property.description}
        className="text-muted-foreground"
      />
      <span className="text-foreground font-mono text-xs">
        {formatValue(property.value)}
        {property.unit ? ` ${property.unit}` : ''}
      </span>
    </div>
  );
}

// The row-level treatment of the same annotations: name and value only, with the
// extent on hover. Keeps a list row readable where the card below would not fit.
// A group is one pill, like a property: its name and how many values it holds,
// with what they are on hover.
export function PropertyBadges({
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
          title={pillTitle(property)}
          className="text-xs px-2 py-0.5 bg-muted text-foreground rounded-full border border-border"
        >
          {property.name}
          {isGroup(property) ? (
            <span className="ml-1 text-muted-foreground">
              {valueCount(valuedProperties([property]).length)}
            </span>
          ) : (
            property.value != null && (
              <span className="ml-1 font-mono text-muted-foreground">
                {formatValue(property.value)}
              </span>
            )
          )}
        </span>
      ))}
      {all.length > shown.length && (
        <span className="text-xs text-muted-foreground">+{all.length - shown.length}</span>
      )}
    </div>
  );
}

function valueCount(count: number): string {
  return `${count} value${count !== 1 ? 's' : ''}`;
}

// Where an annotation sits on its axis, and for a group what it holds, one
// line per property inside it.
function pillTitle(property: ScientificProperty): string | undefined {
  const lines = [
    extentSummary(property.extent),
    ...(isGroup(property) ? (property.properties ?? []).map(propertySummary) : []),
  ].filter(Boolean);
  return lines.length > 0 ? lines.join('\n') : undefined;
}

// Renders a scientific_metadata list, separating the annotations (localised on an
// axis) from the plain properties, with each group as a section holding what is
// inside it. Renders nothing when there is nothing to show.
export function ScientificMetadata({
  properties,
  className = '',
}: {
  properties?: ScientificProperty[];
  className?: string;
}) {
  const { annotations, plain } = splitProperties(properties);
  if (annotations.length === 0 && plain.length === 0) return null;

  return (
    <div className={`card p-6 ${className}`}>
      <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
        <Tag className="w-5 h-5 text-muted-foreground" />
        {annotations.length > 0 ? 'Annotations' : 'Scientific Metadata'}
      </h3>
      {annotations.length > 0 && (
        <div className="space-y-2">
          {annotations.map((property, i) => (
            <AnnotationRow key={`${property.name}-${i}`} property={property} />
          ))}
        </div>
      )}
      {plain.length > 0 && (
        <div className={`text-sm ${annotations.length > 0 ? 'mt-4 pt-3 border-t border-border' : ''}`}>
          {annotations.length > 0 && (
            <p className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-2">
              Other properties
            </p>
          )}
          <PropertyRows properties={plain} />
        </div>
      )}
    </div>
  );
}
