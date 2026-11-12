'use client';

import { ChevronRight, Tag } from 'lucide-react';
import { ScientificProperty } from '@/lib/types';
import {
  AnnotationSet,
  extentRange,
  extentSummary,
  formatCoordinate,
  formatValue,
  groupAnnotations,
  isGroup,
  propertySummary,
  setSpan,
  splitProperties,
  valuedProperties,
} from '@/lib/properties';
import { DescribedName } from '@/components/described-name';

// Where a set of annotations sits on its axis: one annotation's extent, or for
// several, how many and between where.
function setPlacement(set: AnnotationSet): string | null {
  const span = setSpan(set.members);
  if (set.members.length === 1 || span == null) return extentSummary(set.members[0].extent);
  const unit = span.unit ? ` ${span.unit}` : '';
  if (span.end == null) return `${set.members.length} at ${formatCoordinate(span.start)}${unit}`;
  return `${set.members.length} between ${formatCoordinate(span.start)} and ${formatCoordinate(span.end)}${unit}`;
}

// One name's annotations: its value, where they sit, and each of them on
// request. A value of `true` only says the annotation is present, which the row
// already says. An annotated group lists what it holds, all covered by its extent.
function AnnotationSetRow({ set }: { set: AnnotationSet }) {
  const [first] = set.members;
  const many = set.members.length > 1;
  const placement = setPlacement(set);
  const unit = first.extent?.unit ? ` (${first.extent.unit})` : '';
  return (
    <div className="bg-card border border-border rounded-sm p-3">
      <div className="flex items-baseline justify-between gap-2">
        <DescribedName
          name={set.name}
          description={set.description}
          className="font-medium text-foreground"
        />
        {set.value !== undefined && set.value !== true && (
          <span className="text-sm text-foreground font-mono">
            {formatValue(set.value)}
            {first.unit ? ` ${first.unit}` : ''}
          </span>
        )}
      </div>
      {placement && <p className="text-xs text-muted-foreground font-mono mt-1">{placement}</p>}
      {!many && isGroup(first) && (
        <div className="text-sm mt-2">
          <PropertyRows properties={first.properties} />
        </div>
      )}
      {many && (
        <details className="group mt-2">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded-sm text-xs text-muted-foreground hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary [&::-webkit-details-marker]:hidden">
            <ChevronRight className="w-3 h-3 transition-transform group-open:rotate-90" />
            List all {set.members.length}
            {unit}
          </summary>
          <ul className="mt-2 max-h-72 overflow-y-auto grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs font-mono text-foreground">
            {set.members.map((member, i) => (
              <li key={i}>
                {member.extent ? extentRange(member.extent) : '—'}
                {isGroup(member) && (
                  <span className="block font-sans text-muted-foreground">
                    {(member.properties ?? []).map(propertySummary).join(', ')}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
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

// Renders a scientific_metadata list: the properties describing the whole record
// first, then the annotations (localised on an axis), one entry per name and
// value however many there are. Renders nothing when there is nothing to show.
export function ScientificMetadata({
  properties,
  className = '',
}: {
  properties?: ScientificProperty[];
  className?: string;
}) {
  const { annotations, plain } = splitProperties(properties);
  if (annotations.length === 0 && plain.length === 0) return null;
  const sets = groupAnnotations(annotations);

  return (
    <div className={`card p-6 ${className}`}>
      <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
        <Tag className="w-5 h-5 text-muted-foreground" />
        Scientific Metadata
      </h3>
      {plain.length > 0 && (
        <div className="text-sm">
          <PropertyRows properties={plain} />
        </div>
      )}
      {sets.length > 0 && (
        <div className={plain.length > 0 ? 'mt-4 pt-3 border-t border-border' : ''}>
          {plain.length > 0 && (
            <p className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-2">
              Annotations
            </p>
          )}
          <div className="space-y-2">
            {sets.map((set) => (
              <AnnotationSetRow key={`${set.name}-${formatValue(set.value ?? null)}`} set={set} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
