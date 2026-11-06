import { AvailableProperty, Extent, MetadataKind, ScientificProperty } from './types';

export type { AvailableProperty };

// A property with an extent is an annotation: the same property, localised on one
// named axis. Everything else describes the whole record.
export function isAnnotation(property: ScientificProperty): boolean {
  return property.extent != null;
}

// Joins the names of nested properties into a path: `nbi.beam.power`.
export const PATH_SEPARATOR = '.';

// A group holds properties instead of a value.
export function isGroup(property: ScientificProperty): boolean {
  return Array.isArray(property.properties);
}

export interface ValuedProperty {
  path: string;
  property: ScientificProperty;
  // Its own extent, or that of the group it sits in, which covers it.
  extent?: Extent | null;
}

// Every property that holds a value, at any depth, with the path that names it.
// A group is not listed itself: it is only the start of its properties' paths.
// Facets built from loaded records come from this, so they name properties by
// the same paths the server's properties summary does.
//
// With `conditions`, a group instance is gone into only if it meets the
// conditions on its properties, as the server's summary reads a filtered scope.
export function valuedProperties(
  properties?: ScientificProperty[] | null,
  prefix = '',
  extent: Extent | null = null,
  conditions: PropertyCondition[] = []
): ValuedProperty[] {
  return (properties ?? []).flatMap((property) => {
    const path = `${prefix}${property.name}`;
    const covering = property.extent ?? extent;
    if (!isGroup(property)) return [{ path, property, extent: covering }];
    const within = conditionsInside(property.name, conditions);
    if (!meets(property.properties ?? [], within)) return [];
    return valuedProperties(property.properties, `${path}${PATH_SEPARATOR}`, covering, within);
  });
}

// What a property says, in a line: "power 1.6 MW", or for a group
// "beam (source SS, power 1.6 MW)".
export function propertySummary(property: ScientificProperty): string {
  if (isGroup(property)) {
    return `${property.name} (${(property.properties ?? []).map(propertySummary).join(', ')})`;
  }
  const unit = property.unit ? ` ${property.unit}` : '';
  return `${property.name} ${formatValue(property.value)}${unit}`;
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

// "0.20 → 0.45 s" for a span, "0.606 s" for a point. The axis name is left to
// the unit and the property's own name and description, and shown only when
// there is no unit: "channel 3 → 7" says something, "3 → 7" does not.
export function extentSummary(extent?: Extent | null): string | null {
  if (!extent) return null;
  const unit = extent.unit ? ` ${extent.unit}` : '';
  const axis = extent.unit ? '' : `${extent.dimension} `;
  const start = formatCoordinate(extent.start);
  if (extent.end == null) return `${axis}${start}${unit}`;
  return `${axis}${start} → ${formatCoordinate(extent.end)}${unit}`;
}

// A value is text, a number, a boolean or null.
export function formatValue(value: ScientificProperty['value']): string {
  if (value === null || value === undefined) return '—';
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

// `name`, or `name:value` for an equality filter, where `name` is a path for a
// property inside a group. Only the first separator counts, so a value
// containing one survives the round trip unescaped.
export function propertyToken(name: string, value?: ScientificProperty['value']): string {
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
    for (const { path: name, property, extent } of valuedProperties(record.scientific_metadata)) {
      const { value } = property;
      if (value != null) add(values, name, formatValue(value));
      if (!values.has(name)) values.set(name, new Set());
      add(carriers, name, record);
      if (property.unit) add(units, name, property.unit);
      if (extent) dimensions.set(name, extent.dimension);
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

// --- What remains possible -------------------------------------------------
//
// With picks made, each row of a filter panel disables the options that can no
// longer match alongside the picks in the other rows, and a range narrows to the
// values that remain. A row is judged without its own picks, which are
// alternatives to its other options rather than limits on them.

export type Ranges = Record<string, { min?: number; max?: number }>;

// What one row's options can still be. `values` is undefined when the source
// cannot list them, and then no option is disabled.
export interface Remaining {
  values?: string[];
  min?: number | null;
  max?: number | null;
}

// What remains of the property at a path: `null` when nothing does, and
// `undefined` while that is not known.
export type Possible = (name: string) => Remaining | null | undefined;

// The path a token picks on: `nbi.beam.source` for `nbi.beam.source:SW`.
export function tokenPath(token: string): string {
  const end = token.indexOf(SEPARATOR);
  return end === -1 ? token : token.slice(0, end);
}

// The paths that carry a pick, a value or a bound.
export function pickedPaths(tokens: string[], ranges: Ranges = {}): string[] {
  const bounded = Object.entries(ranges)
    .filter(([, range]) => range.min !== undefined || range.max !== undefined)
    .map(([path]) => path);
  return [...new Set([...tokens.map(tokenPath), ...bounded])];
}

// The picks without those on one path: the scope that path's row is judged in.
export function picksWithout(
  path: string,
  tokens: string[],
  ranges: Ranges = {}
): { tokens: string[]; ranges: Ranges } {
  return {
    tokens: tokens.filter((token) => tokenPath(token) !== path),
    ranges: Object.fromEntries(Object.entries(ranges).filter(([name]) => name !== path)),
  };
}

// One pick, parsed: presence with neither `value` nor `bound`, equality with a
// `value`, or a number at or above a `bound` when `lower`, at or below otherwise.
export interface PropertyCondition {
  names: string[];
  value?: string;
  bound?: number;
  lower?: boolean;
}

function conditionsOf(tokens: string[], ranges: Ranges = {}): PropertyCondition[] {
  const conditions: PropertyCondition[] = tokens.map((token) => {
    const path = tokenPath(token);
    return {
      names: path.split(PATH_SEPARATOR),
      value: token.length > path.length ? token.slice(path.length + 1) : undefined,
    };
  });
  for (const [path, range] of Object.entries(ranges)) {
    const names = path.split(PATH_SEPARATOR);
    if (range.min !== undefined) conditions.push({ names, bound: range.min, lower: true });
    if (range.max !== undefined) conditions.push({ names, bound: range.max, lower: false });
  }
  return conditions;
}

// The conditions on the properties inside a group called `name`, relative to it.
function conditionsInside(name: string, conditions: PropertyCondition[]): PropertyCondition[] {
  return conditions
    .filter((condition) => condition.names.length > 1 && condition.names[0] === name)
    .map((condition) => ({ ...condition, names: condition.names.slice(1) }));
}

// The text PostgreSQL renders for a JSON number: the server compares a bound
// only with values that read as one.
const NUMERIC_TEXT = /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/;

function asNumber(value: ScientificProperty['value']): number | undefined {
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && NUMERIC_TEXT.test(value)) return Number(value);
  return undefined;
}

// Whether a property meets a condition, its name aside.
function propertyMeets(property: ScientificProperty, condition: PropertyCondition): boolean {
  if (condition.bound !== undefined) {
    const number = asNumber(property.value);
    if (number === undefined) return false;
    return condition.lower ? number >= condition.bound : number <= condition.bound;
  }
  if (condition.value === undefined) return true;
  if (property.value === null || property.value === undefined) return false;
  return formatValue(property.value).toLowerCase() === condition.value.toLowerCase();
}

// Whether a list of properties meets the conditions, as the server's filter
// reads them. Values of one name are alternatives and each bound must hold;
// the conditions on a group's properties are met together by one instance.
function meets(properties: ScientificProperty[], conditions: PropertyCondition[]): boolean {
  const here = new Map<string, PropertyCondition[]>();
  for (const condition of conditions) {
    if (condition.names.length === 1) {
      here.set(condition.names[0], [...(here.get(condition.names[0]) ?? []), condition]);
    }
  }
  for (const [name, named] of here) {
    const candidates = properties.filter((property) => property.name === name);
    const alternatives = named.filter((condition) => condition.bound === undefined);
    if (
      alternatives.length > 0 &&
      !candidates.some((property) => alternatives.some((c) => propertyMeets(property, c)))
    ) {
      return false;
    }
    for (const bound of named.filter((condition) => condition.bound !== undefined)) {
      if (!candidates.some((property) => propertyMeets(property, bound))) return false;
    }
  }
  const groups = new Set(
    conditions.filter((condition) => condition.names.length > 1).map((c) => c.names[0])
  );
  for (const name of groups) {
    const within = conditionsInside(name, conditions);
    const instance = properties.some(
      (property) => property.name === name && isGroup(property) && meets(property.properties ?? [], within)
    );
    if (!instance) return false;
  }
  return true;
}

// What remains of each path across the records meeting the conditions.
function remainingIn(records: Annotated[], conditions: PropertyCondition[]): Map<string, Remaining> {
  const values = new Map<string, Set<string>>();
  const bounds = new Map<string, { min: number; max: number }>();
  for (const record of records) {
    const properties = record.scientific_metadata ?? [];
    if (!meets(properties, conditions)) continue;
    for (const { path, property } of valuedProperties(properties, '', null, conditions)) {
      const seen = values.get(path) ?? new Set<string>();
      if (property.value !== null && property.value !== undefined) {
        seen.add(formatValue(property.value));
      }
      values.set(path, seen);
      const number = asNumber(property.value);
      if (number !== undefined) {
        const span = bounds.get(path);
        bounds.set(path, {
          min: Math.min(span?.min ?? number, number),
          max: Math.max(span?.max ?? number, number),
        });
      }
    }
  }
  return new Map(
    [...values].map(([path, seen]) => [
      path,
      { values: [...seen], min: bounds.get(path)?.min, max: bounds.get(path)?.max },
    ])
  );
}

// What remains possible in a panel built from records already loaded, worked
// out from those records by the rules the server uses. Undefined with no picks.
export function possibleFromRecords(
  records: Annotated[] | undefined,
  tokens: string[],
  ranges: Ranges = {}
): Possible | undefined {
  const picked = pickedPaths(tokens, ranges);
  if (picked.length === 0) return undefined;
  const scopes = new Map<string, Map<string, Remaining>>();
  const scopeFor = (own: string): Map<string, Remaining> => {
    const known = scopes.get(own);
    if (known) return known;
    const picks = own ? picksWithout(own, tokens, ranges) : { tokens, ranges };
    const scope = remainingIn(records ?? [], conditionsOf(picks.tokens, picks.ranges));
    scopes.set(own, scope);
    return scope;
  };
  return (name) => scopeFor(picked.includes(name) ? name : '').get(name) ?? null;
}
