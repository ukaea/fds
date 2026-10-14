'use client';

import { useId, useRef, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { AvailableProperty, PropertyValues } from '@/lib/types';
import { propertyToken } from '@/lib/properties';
import { DESCRIBED, DescribedName } from '@/components/described-name';

const PILL = 'text-xs px-2.5 py-1 rounded-full border transition-colors';
const IDLE = 'bg-card text-muted-foreground border-border hover:text-foreground hover:border-foreground/40';
const ACTIVE = 'bg-foreground text-background border-foreground';
const HEADING = 'text-muted-foreground uppercase text-[11px] font-bold tracking-wider';

// Shown after a short rest rather than at once, so moving the pointer along a
// row to reach one pill does not flash the count of every pill it crosses.
// Keyboard focus shows it too, but not the focus a click leaves behind, or a
// clicked pill's count would stay open while the pointer moves on.
const COUNT =
  'pointer-events-none absolute left-0 top-full z-20 mt-1 whitespace-nowrap rounded-md border border-border bg-card px-2 py-1 text-[11px] text-foreground shadow-lg invisible opacity-0 transition-opacity group-hover:visible group-hover:opacity-100 group-hover:delay-300 group-has-[:focus-visible]:visible group-has-[:focus-visible]:opacity-100';

// How long the pointer or focus rests on an option before its result is
// fetched. Long enough that crossing a row fetches nothing, short enough that
// the result is usually back before the click.
const PREVIEW_DELAY_MS = 150;

/**
 * Event handlers that fetch an option's result once the pointer or focus has
 * rested on it, so the request a click makes is already answered when the
 * click comes. A click before then cancels it, since the click fetches the
 * same thing itself.
 *
 * One timer per control, because only one of its options can be under the
 * pointer at a time.
 */
function usePreview() {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancel = () => clearTimeout(timer.current);
  return (preview?: () => void) => {
    if (!preview) return {};
    const start = () => {
      cancel();
      timer.current = setTimeout(preview, PREVIEW_DELAY_MS);
    };
    return {
      onPointerEnter: start,
      onFocus: start,
      onPointerLeave: cancel,
      onBlur: cancel,
      onClickCapture: cancel,
    };
  };
}

function countText(count: number, noun: string): string {
  return `${count} ${noun}${count !== 1 ? 's' : ''}`;
}

/**
 * A value to select, with how many records carry it on hover or focus.
 *
 * The count is for the whole scope, not the current selection: it says what
 * the value describes, and the shot count above the list already says what
 * the selection returns.
 */
function Pill({
  label,
  active,
  onClick,
  count,
  noun = 'record',
  onPreview,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
  noun?: string;
  onPreview?: () => void;
}) {
  const id = useId();
  const preview = usePreview();
  const button = (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-describedby={count !== undefined ? id : undefined}
      {...preview(onPreview)}
      className={`${PILL} ${active ? ACTIVE : IDLE}`}
    >
      {label}
    </button>
  );
  if (count === undefined) return button;
  return (
    <span className="relative inline-block group">
      {button}
      <span role="tooltip" id={id} className={COUNT}>
        {countText(count, noun)}
      </span>
    </span>
  );
}

const NAME = 'text-xs text-foreground font-medium';

function PropertyName({ prop }: { prop: AvailableProperty }) {
  return <DescribedName name={prop.name} description={prop.description} className={NAME} />;
}

/**
 * A boolean is three states, not two chips.
 *
 * Two chips would let you select `true` and `false` together, which under OR
 * means the same as selecting neither: a control whose options cancel out. The
 * segmented form says they are alternatives, and keeps all three reachable in
 * one click rather than cycling through them.
 *
 * The ends are rounded on the buttons rather than clipped by the border, which
 * would also clip the counts that open below them.
 */
function TriState({
  name,
  selected,
  onChange,
  counts,
  noun = 'record',
  onPreview,
}: {
  name: string;
  selected: string[];
  onChange: (selected: string[]) => void;
  counts: Map<string, number>;
  noun?: string;
  onPreview?: (selected: string[]) => void;
}) {
  const id = useId();
  const preview = usePreview();
  const yes = propertyToken(name, 'true');
  const no = propertyToken(name, 'false');
  const current = selected.includes(yes) ? yes : selected.includes(no) ? no : null;

  const after = (token: string | null) => {
    const without = selected.filter((t) => t !== yes && t !== no);
    return token ? [...without, token] : without;
  };

  const options: [string, string | null, number | undefined][] = [
    ['any', null, undefined],
    ['yes', yes, counts.get('true')],
    ['no', no, counts.get('false')],
  ];

  return (
    <div className="inline-flex rounded-full border border-border">
      {options.map(([label, token, count], index) => (
        <span key={label} className="relative inline-flex group">
          <button
            type="button"
            aria-pressed={current === token}
            aria-describedby={count !== undefined ? `${id}-${label}` : undefined}
            onClick={() => onChange(after(token))}
            {...preview(
              onPreview && current !== token ? () => onPreview(after(token)) : undefined
            )}
            className={`text-xs px-2.5 py-1 transition-colors ${
              index === 0 ? 'rounded-l-full' : ''
            } ${index === options.length - 1 ? 'rounded-r-full' : ''} ${
              current === token
                ? 'bg-foreground text-background'
                : 'bg-card text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
          </button>
          {count !== undefined && (
            <span role="tooltip" id={`${id}-${label}`} className={COUNT}>
              {countText(count, noun)}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

/**
 * A vocabulary too large to list expands in place: search, then pick.
 *
 * Searched on the server. A device's `objective` runs to hundreds of values
 * several hundred characters long, so shipping all of them to filter in the
 * browser would waste exactly the bandwidth the enumeration cap saves.
 */
function ValueSearch({
  prop,
  valuesUrl,
  selected,
  onChange,
}: {
  prop: AvailableProperty;
  valuesUrl: (name: string, query: string) => string;
  selected: string[];
  onChange: (selected: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const { data, isLoading } = useSWR<PropertyValues>(
    open ? valuesUrl(prop.name, query) : null,
    fetcher,
    { keepPreviousData: true }
  );

  const toggle = (value: string) => {
    const token = propertyToken(prop.name, value);
    onChange(
      selected.includes(token)
        ? selected.filter((t) => t !== token)
        : [...selected, token]
    );
  };

  const chosen = selected.filter((t) => t.startsWith(`${prop.name}:`));

  // A bordered row, because as a bare line of text among chip rows these read
  // as labels rather than as something you can open.
  return (
    <div className="max-w-md rounded-lg border border-border bg-card/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted transition-colors"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground" />
        )}
        {/* A native title: the popover would be clipped by this box's
            overflow-hidden, and a focusable name cannot sit inside a button. */}
        <span
          title={prop.description ?? undefined}
          className={`${NAME} ${prop.description ? DESCRIBED : ''}`}
        >
          {prop.name}
        </span>
        {chosen.length > 0 && (
          <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-foreground text-background">
            {chosen.length}
          </span>
        )}
        <span className="ml-auto text-[11px] text-muted-foreground">
          {prop.distinct} values
        </span>
      </button>

      {/* Selections stay visible when closed: the point of collapsing is to
          hide the nine hundred you did not pick, not the three you did. */}
      {!open && chosen.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap px-3 pb-2">
          {chosen.map((token) => (
            <Pill
              key={token}
              label={token.slice(prop.name.length + 1)}
              active
              onClick={() => onChange(selected.filter((t) => t !== token))}
            />
          ))}
        </div>
      )}

      {open && (
        <div className="px-3 pb-3 border-t border-border pt-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${prop.name}\u2026`}
            className="w-full px-2 py-1 text-xs bg-card border border-border rounded-sm text-foreground placeholder-muted-foreground focus:outline-hidden focus:border-foreground/40"
          />
          <div className="mt-2 max-h-56 overflow-y-auto space-y-0.5">
            {isLoading && !data && (
              <p className="text-xs text-muted-foreground px-1 py-2">Loading\u2026</p>
            )}
            {data?.values.map((entry) => {
              const token = propertyToken(prop.name, entry.value);
              const active = selected.includes(token);
              return (
                <button
                  key={entry.value}
                  type="button"
                  onClick={() => toggle(entry.value)}
                  aria-pressed={active}
                  className={`w-full flex items-baseline justify-between gap-3 text-left text-xs px-2 py-1 rounded-sm transition-colors ${
                    active ? 'bg-foreground text-background' : 'hover:bg-muted'
                  }`}
                >
                  <span className="truncate">{entry.value}</span>
                  <span className={active ? 'opacity-70' : 'text-muted-foreground'}>
                    {entry.records}
                  </span>
                </button>
              );
            })}
            {data && data.values.length === 0 && (
              <p className="text-xs text-muted-foreground px-1 py-2">No matches.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * A quantity is bounded, not picked from.
 *
 * Numbers rather than a slider: the observed spans run from 0.02 to 1,210,000,
 * so a handle's precision would be meaningless at one end of that and useless
 * at the other. The track shows where the bounds sit in the observed range.
 */
// Dragging lands on round numbers, not wherever the pointer happens to be.
// Spans here run from 2.4 seconds to 2.4 million amps, so the step is derived
// from the span and rounded to a 1, 2 or 5, the same reasoning that picks axis
// ticks. Aims for roughly fifty positions across the track, which is coarse
// enough to be predictable; the text inputs stay unquantised for finer work.
function niceStep(span: number): number {
  if (!Number.isFinite(span) || span <= 0) return 1;
  const raw = span / 50;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalised = raw / magnitude;
  const rounded = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return rounded * magnitude;
}

function RangeInput({
  prop,
  range,
  onChange,
}: {
  prop: AvailableProperty;
  range: { min?: number; max?: number };
  onChange: (range: { min?: number; max?: number }) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<'min' | 'max' | null>(null);

  const low = prop.min ?? 0;
  const high = prop.max ?? 0;
  const span = high - low || 1;
  const from = range.min ?? low;
  const to = range.max ?? high;

  const pct = (value: number) => ((value - low) / span) * 100;
  const clamp = (value: number) => Math.min(high, Math.max(low, value));

  const step = niceStep(span);
  // Rounding to the step's own precision, or 0.05 steps accumulate into
  // 0.15000000000000002.
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  const round = (value: number) => Number(value.toFixed(decimals));

  // The steps are multiples of the step size, which almost never divide the
  // span exactly, so both ends finish with a partial interval. Those ends are
  // the observed minimum and maximum, the most useful positions on the
  // control, so they are offered alongside the multiples rather than rounded
  // away. Without them the top of plasma_current_max is 1,400,000 and its real
  // maximum of 1,418,442 cannot be reached by dragging at all.
  const snap = (value: number) => {
    const target = clamp(value);
    const candidates = [
      low,
      high,
      round(Math.floor(target / step) * step),
      round(Math.ceil(target / step) * step),
    ].filter((candidate) => candidate >= low && candidate <= high);
    return candidates.reduce((best, candidate) =>
      Math.abs(candidate - target) < Math.abs(best - target) ? candidate : best
    );
  };

  // Drag handled on the track rather than with two overlaid range inputs: the
  // handles would otherwise fight over the pointer wherever they overlap, which
  // is exactly where you want to grab one of them.
  const positionFrom = (clientX: number) => {
    const box = track.current?.getBoundingClientRect();
    if (!box) return low;
    return clamp(low + ((clientX - box.left) / box.width) * span);
  };

  const onPointerDown = (handle: 'min' | 'max') => (e: React.PointerEvent) => {
    e.preventDefault();
    (e.target as Element).setPointerCapture(e.pointerId);
    setDragging(handle);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return;
    const value = snap(positionFrom(e.clientX));
    onChange(
      dragging === 'min'
        ? { ...range, min: Math.min(value, to) }
        : { ...range, max: Math.max(value, from) }
    );
  };

  const nudge = (handle: 'min' | 'max', by: number) => {
    const value = snap((handle === 'min' ? from : to) + by * step);
    onChange(
      handle === 'min'
        ? { ...range, min: Math.min(value, to) }
        : { ...range, max: Math.max(value, from) }
    );
  };

  const parse = (raw: string) => (raw === '' ? undefined : Number(raw));

  const handle = (which: 'min' | 'max', value: number) => (
    <button
      type="button"
      role="slider"
      aria-label={`${prop.name} ${which}`}
      aria-valuemin={low}
      aria-valuemax={high}
      aria-valuenow={value}
      onPointerDown={onPointerDown(which)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') nudge(which, -1);
        if (e.key === 'ArrowRight') nudge(which, 1);
      }}
      style={{ left: `${pct(value)}%` }}
      className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-foreground border-2 border-background shadow-sm cursor-grab active:cursor-grabbing touch-none focus:outline-hidden focus:ring-2 focus:ring-primary"
    />
  );

  const NUMBER_INPUT =
    'w-24 px-2 py-0.5 text-xs bg-card border border-border rounded-sm text-foreground ' +
    'placeholder-muted-foreground focus:outline-hidden focus:border-foreground/40 ' +
    '[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none ' +
    '[&::-webkit-inner-spin-button]:appearance-none';

  return (
    <div className="max-w-xs">
      {/* No separate range text: the empty inputs show it as placeholders. */}
      <PropertyName prop={prop} />

      <div
        ref={track}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragging(null)}
        onPointerCancel={() => setDragging(null)}
        className="relative h-4 mt-2 mb-2.5 touch-none"
      >
        <div className="absolute top-1/2 -translate-y-1/2 w-full h-1 rounded-full bg-muted" />
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1 rounded-full bg-foreground/60"
          style={{ left: `${pct(from)}%`, width: `${pct(to) - pct(from)}%` }}
        />
        {handle('min', from)}
        {handle('max', to)}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="number"
          value={range.min ?? ''}
          placeholder={String(Number(low.toPrecision(10)))}
          onChange={(e) => onChange({ ...range, min: parse(e.target.value) })}
          className={NUMBER_INPUT}
        />
        <span className="text-xs text-muted-foreground">to</span>
        <input
          type="number"
          value={range.max ?? ''}
          placeholder={String(Number(high.toPrecision(10)))}
          onChange={(e) => onChange({ ...range, max: parse(e.target.value) })}
          className={NUMBER_INPUT}
        />
        {prop.unit && <span className="text-xs text-muted-foreground">{prop.unit}</span>}
      </div>
    </div>
  );
}

const BOOLEAN_VALUES = new Set(['true', 'false']);

function isBoolean(prop: AvailableProperty): boolean {
  return !!prop.values?.length && prop.values.every((v) => BOOLEAN_VALUES.has(v));
}

function TermRow({
  prop,
  valuesUrl,
  selected,
  onChange,
  noun,
  onPreview,
}: {
  prop: AvailableProperty;
  valuesUrl: (name: string, query: string) => string;
  selected: string[];
  onChange: (selected: string[]) => void;
  noun?: string;
  onPreview?: (selected: string[]) => void;
}) {
  // The summary lists a property's values without how many records carry
  // each, so the counts come from its values endpoint: one request per row,
  // made with the panel so they are there before anything is hovered. A panel
  // without a values endpoint shows no counts.
  const { data: counted } = useSWR<PropertyValues>(
    prop.values ? valuesUrl(prop.name, '') || null : null,
    fetcher
  );
  const counts = new Map<string, number>(
    counted?.values.map((entry) => [entry.value, entry.records])
  );

  const toggled = (token: string) =>
    selected.includes(token) ? selected.filter((t) => t !== token) : [...selected, token];

  if (isBoolean(prop)) {
    return (
      <div className="space-y-1.5">
        <div>
          <PropertyName prop={prop} />
        </div>
        <TriState
          name={prop.name}
          selected={selected}
          onChange={onChange}
          counts={counts}
          noun={noun}
          onPreview={onPreview}
        />
      </div>
    );
  }

  if (!prop.values) {
    return (
      <ValueSearch
        prop={prop}
        valuesUrl={valuesUrl}
        selected={selected}
        onChange={onChange}
      />
    );
  }

  // The name is a heading, not a control: clicking a property rather than a
  // value of it was the thing nobody could explain.
  return (
    <div className="space-y-1.5">
      <div>
        <PropertyName prop={prop} />
      </div>
      <div className="flex items-baseline gap-2 flex-wrap">
        {prop.values.map((value) => {
          const token = propertyToken(prop.name, value);
          return (
            <Pill
              key={value}
              label={prop.unit ? `${value} ${prop.unit}` : value}
              active={selected.includes(token)}
              onClick={() => onChange(toggled(token))}
              count={counts.get(value)}
              noun={noun}
              onPreview={onPreview && (() => onPreview(toggled(token)))}
            />
          );
        })}
      </div>
    </div>
  );
}

/**
 * Filter controls for one scope's scientific metadata.
 *
 * Three sections, because the panel used to treat every property as the same
 * kind of thing and they are not. An annotation is a claim about a region of the
 * data and carries a dimension; a term is drawn from a vocabulary and is picked
 * from; a quantity is a magnitude and is bounded. Prose never appears: it
 * describes one record rather than classifying it, which is what made the old
 * presence row a dumping ground. Only annotations carry a heading: chips and
 * range controls already show which of the other two a property is.
 *
 * Values of one property OR together and different properties AND, which is
 * what the server does with repeated parameters and what selecting two chips in
 * one row means.
 */
export function PropertyFilter({
  label,
  properties,
  selected,
  onChange,
  ranges = {},
  onRangesChange,
  valuesUrl,
  noun,
  onPreview,
}: {
  // Only needed where two panels sit together and must be told apart.
  label?: string;
  properties: AvailableProperty[];
  selected: string[];
  onChange: (selected: string[]) => void;
  ranges?: Record<string, { min?: number; max?: number }>;
  onRangesChange?: (ranges: Record<string, { min?: number; max?: number }>) => void;
  valuesUrl?: (name: string, query: string) => string;
  // What the counts count, in the singular: "shot" reads "3514 shots".
  noun?: string;
  // Called with the selection a click on the option under the pointer would
  // make, so the caller can fetch that selection's results ahead of the click.
  onPreview?: (selected: string[]) => void;
}) {
  if (properties.length === 0) return null;

  const annotations = properties.filter((f) => f.dimension);
  const terms = properties.filter((f) => !f.dimension && f.kind === 'term');
  const quantities = properties.filter((f) => !f.dimension && f.kind === 'quantity');

  const noValues = () => '';
  const boundedRanges = Object.values(ranges).filter(
    (r) => r.min !== undefined || r.max !== undefined
  );
  const hasFilters = selected.length > 0 || boundedRanges.length > 0;

  const clear = () => {
    onChange([]);
    onRangesChange?.({});
  };

  const section = (title: string, hint: string | null, rows: React.ReactNode) => (
    <div>
      <p className={HEADING}>
        {title}
        {hint && <span className="ml-2 font-normal normal-case opacity-70">{hint}</span>}
      </p>
      <div className="mt-3.5 space-y-3">{rows}</div>
    </div>
  );

  const clearButton = hasFilters && (
    <button
      type="button"
      onClick={clear}
      className={`text-xs text-muted-foreground hover:text-foreground transition-colors ${
        label ? '' : 'absolute top-4 right-4'
      }`}
    >
      Clear
    </button>
  );

  return (
    <div className="card relative p-6 mb-6 space-y-10">
      {label && (
        <div className="flex items-baseline justify-between gap-4">
          <p className={HEADING}>{label}</p>
          {clearButton}
        </div>
      )}

      {annotations.length > 0 &&
        section(
          'Annotations',
          'localised in the data',
          annotations.map((prop) => (
            <div key={prop.name} className="flex items-center gap-3 flex-wrap">
              <TermRow
                prop={prop}
                valuesUrl={valuesUrl ?? noValues}
                selected={selected}
                onChange={onChange}
                noun={noun}
                onPreview={onPreview}
              />
              <span className="text-[11px] text-muted-foreground">
                on {prop.dimension}
              </span>
            </div>
          ))
        )}

      {terms.length > 0 && (
        <div>
          <div className="space-y-3">
            {terms
              .filter((f) => f.values)
              .map((prop) => (
                <TermRow
                  key={prop.name}
                  prop={prop}
                  valuesUrl={valuesUrl ?? noValues}
                  selected={selected}
                  onChange={onChange}
                  noun={noun}
                  onPreview={onPreview}
                />
              ))}
          </div>
          {/* A vocabulary you open is a different control from a row of chips,
              so it gets its own block rather than reading as one more row. */}
          <div className="mt-6 space-y-2.5">
            {terms
              .filter((f) => !f.values)
              .map((prop) => (
                <TermRow
                  key={prop.name}
                  prop={prop}
                  valuesUrl={valuesUrl ?? noValues}
                  selected={selected}
                  onChange={onChange}
                  noun={noun}
                  onPreview={onPreview}
                />
              ))}
          </div>
        </div>
      )}

      {quantities.length > 0 && onRangesChange && (
        <div>
          {/* As many columns as the panel has room for: one in the side column,
              several across a full-width page, where a single stacked column
              left a tall thin strip beside empty space. */}
          <div className="grid gap-x-12 gap-y-8 grid-cols-[repeat(auto-fill,minmax(15rem,1fr))]">
            {quantities.map((prop) => (
              <RangeInput
                key={prop.name}
                prop={prop}
                range={ranges[prop.name] ?? {}}
                onChange={(range) => onRangesChange({ ...ranges, [prop.name]: range })}
              />
            ))}
          </div>
        </div>
      )}

      {/* Last, so its arrival does not add space-y margin above the first
          section: it is positioned out of the flow anyway. */}
      {!label && clearButton}
    </div>
  );
}
