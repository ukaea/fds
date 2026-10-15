'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { Cpu, Database, Layers } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { AvailableProperties, Collection, Dataset, Device, Source } from '@/lib/types';
import { propertyQuery, withQuery } from '@/lib/properties';
import { usePagedList } from '@/lib/use-paged-list';
import { PropertyFilter } from '@/components/property-filter';
import { SidePanelLayout } from '@/components/side-panel-layout';
import { LoadMore } from '@/components/load-more';
import { DatasetCard } from '@/components/dataset-card';
import { RunCard } from '@/components/run-card';
import { SearchBox } from '@/components/search-box';

const PAGE_SIZE = 50;
const DOCS = 'https://ukaea.github.io/fds/data-model/collection/#making-a-run-discoverable';

const PILL = 'text-xs px-2.5 py-1 rounded-full border transition-colors';
const IDLE = 'bg-card text-muted-foreground border-border hover:text-foreground hover:border-foreground/40';
const ACTIVE = 'bg-foreground text-background border-foreground';
const HEADING = 'text-muted-foreground uppercase text-[11px] font-bold tracking-wider';

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`${PILL} ${active ? ACTIVE : IDLE}`}
    >
      {children}
    </button>
  );
}

/** One of a few named options, or none of them: "any device". */
function Choice({
  title,
  anyLabel,
  options,
  selected,
  onChange,
}: {
  title: string;
  anyLabel: string;
  options: { value: string; label: string }[];
  selected: string | null;
  onChange: (value: string | null) => void;
}) {
  if (options.length === 0) return null;
  return (
    <div>
      <p className={HEADING}>{title}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Pill active={selected === null} onClick={() => onChange(null)}>
          {anyLabel}
        </Pill>
        {options.map((option) => (
          <Pill
            key={option.value}
            active={selected === option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </Pill>
        ))}
      </div>
    </div>
  );
}

/**
 * A chip for one code, shown only if the code generated a simulated dataset
 * under `base`.
 *
 * Software sources include acquisition schedulers and analysis codes as well as
 * simulation codes, and a source does not say which it is. Asking for one
 * simulated dataset it generated tells them apart.
 */
function CodeOption({
  base,
  code,
  selected,
  onChange,
}: {
  base: string;
  code: string;
  selected: string | null;
  onChange: (value: string | null) => void;
}) {
  const { data } = useSWR<Dataset[]>(
    `${base}/datasets?activity_type=simulation&source=${encodeURIComponent(code)}&limit=1`,
    fetcher
  );
  if (!data?.length && selected !== code) return null;
  return (
    <Pill active={selected === code} onClick={() => onChange(code)}>
      {code}
    </Pill>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  count,
  hint,
}: {
  icon: typeof Layers;
  title: string;
  count?: string;
  hint?: string;
}) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-3">
        <div className="bg-muted p-2 rounded-lg text-foreground">
          <Icon className="w-5 h-5" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">{title}</h2>
        {count && <span className="text-sm text-muted-foreground">({count})</span>}
      </div>
      {hint && <p className="text-sm text-muted-foreground mt-2">{hint}</p>}
    </div>
  );
}

function shown(items: unknown[] | undefined, done: boolean): string | undefined {
  if (!items) return undefined;
  return done ? `${items.length}` : `${items.length}+`;
}

/**
 * Simulation runs and the data they produced, across devices and shots.
 *
 * Runs are listed through their bundles: collections whose activity_id names a
 * simulation run, carrying what the run says it simulated. The property filter
 * narrows these. Simulated datasets are listed after them, whether bundled or
 * not, so a run without a bundle can still be found through its outputs.
 *
 * The shot box narrows both lists, as you type, to the runs on shots whose ID
 * starts with what is typed, on the chosen device or on any device.
 *
 * With `deviceName`, only that device's runs are listed and the device filter is
 * hidden. Both lists then include runs that modelled no shot, such as
 * predictive scenarios.
 */
export function SimulationBrowser({ deviceName }: { deviceName?: string }) {
  const [source, setSource] = useState<string | null>(null);
  const [device, setDevice] = useState<string | null>(null);
  const [propertyTokens, setPropertyTokens] = useState<string[]>([]);
  const [shotInput, setShotInput] = useState('');
  const shotPrefix = shotInput.trim();

  const { data: sources } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);
  const { data: devices } = useSWR<Device[]>(deviceName ? null : `${API_BASE}/devices/`, fetcher);

  const scope = deviceName ?? device;
  const base = scope ? `${API_BASE}/devices/${scope}` : API_BASE;
  const runFilters = [
    'activity_type=simulation',
    source ? `source=${encodeURIComponent(source)}` : '',
    shotPrefix ? `shot_id_prefix=${encodeURIComponent(shotPrefix)}` : '',
  ];

  // The property chips come from a summary of every run the code and device
  // filters leave, not from the runs loaded so far. The summary leaves out the
  // property filter itself, so picking one chip does not hide the others.
  const { data: runProperties } = useSWR<AvailableProperties>(
    withQuery(`${base}/collections/properties`, ...runFilters),
    fetcher
  );
  const runs = usePagedList<Collection>(
    withQuery(`${base}/collections`, ...runFilters, propertyQuery('property', propertyTokens)),
    PAGE_SIZE
  );
  const datasets = usePagedList<Dataset>(
    withQuery(`${base}/datasets`, ...runFilters),
    PAGE_SIZE
  );

  const codes = (sources ?? []).filter((s) => s.kind === 'software').map((s) => s.name);
  const deviceOptions = (devices ?? []).map((d) => ({ value: d.name, label: d.title || d.name }));
  const filtered = source !== null || device !== null || propertyTokens.length > 0 || shotPrefix !== '';

  const side = (
    <>
      <div className="card p-6 mb-6 space-y-8">
        {codes.length > 0 && (
          <div>
            <p className={HEADING}>Code</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Pill active={source === null} onClick={() => setSource(null)}>
                Any code
              </Pill>
              {codes.map((code) => (
                <CodeOption
                  key={code}
                  base={base}
                  code={code}
                  selected={source}
                  onChange={setSource}
                />
              ))}
            </div>
          </div>
        )}
        {!deviceName && (
          <Choice
            title="Device"
            anyLabel="Any device"
            options={deviceOptions}
            selected={device}
            onChange={setDevice}
          />
        )}
        <div>
          <p className={HEADING}>Shot</p>
          <div className="mt-3">
            <SearchBox value={shotInput} onChange={setShotInput} label="Shot ID" inputMode="numeric" />
          </div>
          {shotPrefix && (
            <p className="text-xs text-muted-foreground mt-2">
              Runs on shots whose ID starts with {shotPrefix}
              {scope ? '' : ', on any device'}.
            </p>
          )}
        </div>
      </div>
      <PropertyFilter
        label="What the run simulated"
        properties={runProperties?.properties ?? []}
        selected={propertyTokens}
        onChange={setPropertyTokens}
      />
    </>
  );

  return (
    <SidePanelLayout side={side}>
      <section className="mb-12">
        <SectionHeading
          icon={Layers}
          title="Runs"
          count={shown(runs.items, runs.done)}
          hint="Simulation runs bundled as a citable collection, with what each says it simulated."
        />
        {runs.isLoading && !runs.items && (
          <div className="card p-6 text-center text-muted-foreground">Loading runs…</div>
        )}
        {runs.error && (
          <div className="card p-6 text-center text-destructive">Failed to load runs.</div>
        )}
        {runs.items && runs.items.length === 0 && (
          <div className="text-center py-12 px-6 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
            <Cpu className="w-10 h-10 mx-auto mb-3 opacity-30" />
            {filtered ? (
              <p>No runs match these filters.</p>
            ) : (
              <>
                <p className="font-medium">No simulation runs have been bundled yet.</p>
                <p className="text-sm mt-1 max-w-xl mx-auto">
                  A run is listed here once it has a bundle: a collection of its outputs whose
                  activity_id names the run.{' '}
                  <a href={DOCS} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    How to make a run discoverable
                  </a>
                </p>
              </>
            )}
          </div>
        )}
        {!!runs.items?.length && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {runs.items.map((run) => (
              <RunCard key={run.id} collection={run} />
            ))}
          </div>
        )}
        <LoadMore onLoad={runs.loadMore} loading={runs.loadingMore} done={runs.done} />
      </section>

      <section>
        <SectionHeading
          icon={Database}
          title="Simulated datasets"
          count={shown(datasets.items, datasets.done)}
          hint={
            propertyTokens.length > 0
              ? 'Every dataset a simulation generated, bundled or not. The filter on what a run simulated applies to runs only.'
              : 'Every dataset a simulation generated, bundled or not.'
          }
        />
        {datasets.error && (
          <div className="card p-6 text-center text-destructive">Failed to load datasets.</div>
        )}
        {datasets.items && datasets.items.length === 0 && (
          <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
            {filtered ? 'No simulated datasets match these filters.' : 'No simulated datasets registered yet.'}
          </div>
        )}
        {!!datasets.items?.length && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {datasets.items.map((dataset) => (
              <DatasetCard key={dataset.id ?? dataset.name} dataset={dataset} showContext />
            ))}
          </div>
        )}
        <LoadMore onLoad={datasets.loadMore} loading={datasets.loadingMore} done={datasets.done} />
      </section>
    </SidePanelLayout>
  );
}
