import { AvailableProperty, Extent, MetadataKind, ScientificProperty } from './types';

export type { AvailableProperty };

// A property with an extent is an annotation: the same property, localised on one
// named axis. Everything else is a plain scalar property.
export function isAnnotation(property: ScientificProperty): boolean {
  return property.extent != null;
}

export function splitProperties(properties?: ScientificProperty[]): {
  annotations: ScientificProperty[];
  plain: ScientificProperty[];
} {
  const all = properties ?? [];
  return {
    annotations: all.filter(isAnnotation),
    plain: all.filter((p) => !isAnnotation(p)),
  };
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

// `name`, or `name:value` for an equality filter. Only the first separator
// counts, so a value containing one survives the round trip unescaped.
export function propertyToken(name: string, value?: unknown): string {
  if (value === undefined) return name;
  return `${name}${SEPARATOR}${formatValue(value)}`;
}

// Past this many distinct values a name stops being a prop: a chip per value
// is unusable and an equality filter on a measurement matches one record. Kept
// equal to the server's default so both sources of properties agree on what counts
// as enumerable.
export const MAX_INLINE_VALUES = 20;

// Above this share of distinct-values-per-record a name is prose rather than a
// vocabulary. Mirrors the server so both sources of properties agree.
const PROSE_RATIO = 0.5;
const RATIO_FLOOR = 20;

// Render a magnitude with its unit. Large values get thousands separators
// rather than an exponent: a plasma current reads as 1,418,442 A on the axis
// and in the input beside it, where 1.42e+6 reads as neither. Only genuinely
// tiny values fall back to an exponent, where separators would not help.
export function formatQuantity(value: number, unit?: string | null): string {
  const magnitude = Math.abs(value);
  let text: string;
  if (magnitude > 0 && magnitude < 0.001) {
    text = value.toExponential(2);
  } else if (magnitude >= 1000) {
    text = Math.round(value).toLocaleString('en-GB');
  } else {
    text = String(Number(value.toPrecision(4)));
  }
  return unit ? `${text} ${unit}` : text;
}

function inferKind(distinct: number, records: number, numeric: boolean): MetadataKind {
  const repeats = records >= RATIO_FLOOR && distinct / records < PROSE_RATIO;
  const small = distinct > 0 && distinct <= 200;
  if (small && (repeats || records < RATIO_FLOOR)) return 'term';
  if (numeric) return 'quantity';
  return repeats ? 'term' : 'text';
}

// The scientific metadata present across a set of records, in the shape the
// server returns for the scopes that have a properties endpoint.
//
// Derived from the records in hand, so it describes the page that was loaded
// rather than the collection. Where that distinction matters, fetch the properties
// instead.
export function availableProperties(
  records?: Annotated[],
  maxValues: number = MAX_INLINE_VALUES
): AvailableProperty[] {
  const values = new Map<string, Set<string>>();
  const carriers = new Map<string, Set<Annotated>>();
  const units = new Map<string, Set<string>>();
  const dimensions = new Map<string, string>();
  const declared = new Map<string, Set<string>>();
  const numerics = new Map<string, boolean>();
  const bounds = new Map<string, { min: number; max: number }>();

  const add = <T,>(map: Map<string, Set<T>>, key: string, item: T) => {
    const set = map.get(key) ?? new Set<T>();
    set.add(item);
    map.set(key, set);
  };

  for (const record of records ?? []) {
    for (const property of record.scientific_metadata ?? []) {
      const { name, value } = property;
      // An object value has no sensible pill label and no useful equality
      // filter, so the name is offered on its own.
      if (value != null && typeof value !== 'object') {
        add(values, name, formatValue(value));
      }
      if (!values.has(name)) values.set(name, new Set());
      add(carriers, name, record);
      if (property.unit) add(units, name, property.unit);
      if (property.extent) dimensions.set(name, property.extent.dimension);
      if (property.kind) add(declared, name, property.kind);

      const isNumber = typeof value === 'number';
      numerics.set(name, (numerics.get(name) ?? true) && isNumber);
      if (isNumber) {
        const seen = bounds.get(name);
        bounds.set(name, {
          min: Math.min(seen?.min ?? value, value),
          max: Math.max(seen?.max ?? value, value),
        });
      }
    }
  }

  return [...values.entries()]
    .map(([name, seen]) => {
      const records_ = carriers.get(name)?.size ?? 0;
      const seenUnits = units.get(name);
      const seenKinds = declared.get(name);
      const numeric = numerics.get(name) ?? false;
      // A provider that disagrees with itself about a name's kind is not
      // declaring anything, so fall back to inference.
      const kind =
        seenKinds?.size === 1
          ? ([...seenKinds][0] as MetadataKind)
          : inferKind(seen.size, records_, numeric);
      const span = bounds.get(name);
      return {
        name,
        records: records_,
        distinct: seen.size,
        kind,
        // A name recorded in two units has no single unit to report.
        unit: seenUnits?.size === 1 ? [...seenUnits][0] : undefined,
        dimension: dimensions.get(name),
        min: kind === 'quantity' ? span?.min : undefined,
        max: kind === 'quantity' ? span?.max : undefined,
        values:
          kind === 'term' && seen.size > 0 && seen.size <= maxValues
            ? sortValues([...seen])
            : undefined,
      };
    })
    // Prose describes one record rather than classifying it, so it is not a filter.
    .filter((prop) => prop.kind !== 'text')
    .sort(
      (a, b) =>
        Number(a.dimension === undefined) - Number(b.dimension === undefined) ||
        Number(a.kind === 'quantity') - Number(b.kind === 'quantity') ||
        Number(a.values === undefined) - Number(b.values === undefined) ||
        a.distinct - b.distinct ||
        a.name.localeCompare(b.name)
    );
}

// Numerically when the values are numbers, alphabetically otherwise: a target
// range of 400, 700 and 1000 reads in that order; as text it reads 1000 first.
function sortValues(values: string[]): string[] {
  const numeric = values.every((v) => v !== '' && !Number.isNaN(Number(v)));
  return numeric
    ? [...values].sort((a, b) => Number(a) - Number(b))
    : [...values].sort();
}

// Repeated parameters AND together server-side, which is exactly how the chips
// combine. Returns '' for no tokens, which withQuery then drops: an unfiltered
// listing keeps the url the prop fetch uses, so SWR makes one request for both.
export function propertyQuery(
  parameter: 'property' | 'shot_property',
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
