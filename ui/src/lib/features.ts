import { Extent, ScientificProperty } from './types';

// A property with an extent is a feature: the same property, localised on one
// named axis. Everything else is a plain scalar property.
export function isFeature(property: ScientificProperty): boolean {
  return property.extent != null;
}

export function splitProperties(properties?: ScientificProperty[]): {
  features: ScientificProperty[];
  plain: ScientificProperty[];
} {
  const all = properties ?? [];
  return { features: all.filter(isFeature), plain: all.filter((p) => !isFeature(p)) };
}

// Numbers on an axis span many orders of magnitude (0.606 s, 18000 Hz), so keep
// significant digits rather than a fixed decimal count.
function formatCoordinate(value: number): string {
  if (value === 0) return '0';
  const magnitude = Math.abs(value);
  if (magnitude >= 1000 || magnitude < 0.001) return value.toExponential(2);
  return String(Number(value.toPrecision(4)));
}

// "time 0.20 → 0.45 s" for a span, "time 0.606 s" for a point. The dimension is
// always shown: the axis is what makes the numbers meaningful.
export function extentSummary(extent?: Extent | null): string | null {
  if (!extent) return null;
  const unit = extent.unit ? ` ${extent.unit}` : '';
  const start = formatCoordinate(extent.start);
  if (extent.end == null) return `${extent.dimension} ${start}${unit}`;
  return `${extent.dimension} ${start} → ${formatCoordinate(extent.end)}${unit}`;
}

// scientific_metadata values are any JSON type, so render them without assuming.
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

// --- Filtering ---------------------------------------------------------------
//
// The listing endpoints take a repeated `annotation` parameter, either a bare
// `name` (the property is present) or `name:value` (present with that value).
// The helpers below build those tokens and derive the choices on offer from the
// records themselves, so nothing here needs a vocabulary to filter against.

const SEPARATOR = ':';

export interface Annotated {
  scientific_metadata?: ScientificProperty[];
}

export interface AnnotationFacet {
  name: string;
  values: string[];
}

// `name`, or `name:value` for an equality filter. Only the first separator
// counts, so a value containing one survives the round trip unescaped.
export function annotationToken(name: string, value?: unknown): string {
  if (value === undefined) return name;
  return `${name}${SEPARATOR}${formatValue(value)}`;
}

// The annotations present across a set of records, as one row per name with the
// distinct values seen under it. Every property counts, not just the ones with an
// extent: the server filters on all of scientific_metadata.
export function annotationFacets(records?: Annotated[]): AnnotationFacet[] {
  const values = new Map<string, Set<string>>();
  for (const record of records ?? []) {
    for (const property of record.scientific_metadata ?? []) {
      const seen = values.get(property.name) ?? new Set<string>();
      // An object value has no sensible pill label and no useful equality
      // filter, so the name is offered on its own.
      if (property.value != null && typeof property.value !== 'object') {
        seen.add(formatValue(property.value));
      }
      values.set(property.name, seen);
    }
  }
  return [...values.entries()]
    .map(([name, seen]) => ({ name, values: [...seen].sort() }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// Repeated parameters AND together server-side, which is exactly how the chips
// combine. Returns '' for no tokens, which withQuery then drops: an unfiltered
// listing keeps the url the facet fetch uses, so SWR makes one request for both.
export function annotationQuery(
  parameter: 'annotation' | 'shot_annotation',
  tokens: string[]
): string {
  if (tokens.length === 0) return '';
  const query = new URLSearchParams();
  for (const token of tokens) query.append(parameter, token);
  return query.toString();
}

// Append query parts to a url that may or may not already carry some.
export function withQuery(url: string, ...parts: string[]): string {
  const query = parts.filter(Boolean).join('&');
  if (!query) return url;
  return `${url}${url.includes('?') ? '&' : '?'}${query}`;
}
