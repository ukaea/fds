'use client';

import { useState, useEffect, useRef, type ReactNode } from 'react';
import Link from 'next/link';
import { Database, Lock, Unlock, Download, Activity, ChevronRight, MapPin, SlidersHorizontal, Highlighter, Copy, Check } from 'lucide-react';
import { useSession, signIn } from "next-auth/react";
import useSWR from 'swr';
import { fetcher, API_BASE } from '@/lib/api';
import { Activity as ActivityType, Collection, Dataset, Distribution, Source } from '@/lib/types';
import ProvenanceGraph from '@/components/ProvenanceGraph';
import { ScientificMetadata } from '@/components/properties';
import { RelatedGroup } from '@/components/related-data';
import { useDeviceLabel } from '@/lib/use-device-label';
import { citation, resolveIdentifier } from '@/lib/identifiers';
import type { JsonLd } from '@/lib/identifier-page';
import { JsonLdPanel } from '@/components/jsonld-panel';
import { HeatmapCanvas } from '@/components/heatmap';

function isZarr(mediaType?: string | null): boolean {
  return Boolean(mediaType?.toLowerCase().includes('zarr'));
}

// The in-browser reader speaks plain Zarr. An icechunk store is Zarr underneath
// but only opens through icechunk.
function canVisualise(d: Distribution): boolean {
  return isZarr(d.media_type) && !d.media_type!.toLowerCase().includes('icechunk');
}

function distributionLabel(d: Distribution): string {
  return d.format || d.media_type || 'Unknown format';
}

function Property({ label, children, last = false }: { label: string; children: ReactNode; last?: boolean }) {
  return (
    <div className={`flex flex-col justify-start py-1 ${last ? '' : 'border-b border-border pb-2'}`}>
      <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">{label}</span>
      {children}
    </div>
  );
}

const DATE: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'long', day: 'numeric' };
const INSTANT: Intl.DateTimeFormatOptions = { ...DATE, hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC', timeZoneName: 'short' };

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access is denied outside a secure context; the value is
      // still on the page to select.
    }
  };
  return (
    <button type="button" onClick={copy} aria-label="Copy" className="shrink-0 text-muted-foreground hover:text-foreground transition-colors">
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

// One line however long the value, so it cannot spill out of a narrow card.
// The whole of it is in the tooltip and on the clipboard.
function TruncatedValue({ value }: { value: string }) {
  return (
    <span className="flex items-center gap-2">
      <span className="font-mono text-foreground truncate" title={value}>{value}</span>
      <CopyButton value={value} />
    </span>
  );
}

// How to open one dataset's bytes: either short-lived credentials FDS minted, or
// anonymous access to a store that is already public. The endpoint always comes
// from FDS rather than being assumed, because the data need not be in the demo's
// own object store.
interface DataAccess {
  endpointUrl: string;
  anon: boolean;
  accessKeyId?: string;
  secretAccessKey?: string;
  sessionToken?: string;
  region?: string;
}

// Only used if FDS somehow returns no endpoint; the demo's own store.
const MINIO_FALLBACK = "http://localhost:9000";

// Public stores serve unsigned GETs, and signing them with no credentials would
// be rejected outright.
async function makeFetcher(access: DataAccess): Promise<(target: string) => Promise<Response>> {
  if (access.anon) return (target: string) => fetch(target);
  const { AwsClient } = await import('aws4fetch');
  const awsClient = new AwsClient({
    accessKeyId: access.accessKeyId as string,
    secretAccessKey: access.secretAccessKey as string,
    sessionToken: access.sessionToken,
    region: access.region || 'us-east-1',
    service: 's3'
  });
  return (target: string) => awsClient.fetch(target);
}

// "s3://bucket/some/prefix" against a given endpoint. Path-style addressing, so
// the bucket stays in the path and the same code serves MinIO and any public store.
function objectUrl(endpointUrl: string, s3Path: string): { origin: string; path: string } {
  const url = new URL(s3Path.replace("s3://", `${endpointUrl.replace(/\/$/, "")}/`));
  return { origin: url.origin, path: url.pathname.replace(/^\//, "") };
}

// Store reads are immutable at a given URL, and every dataset on a shot resolves
// through the same root listing, so the cache is shared across navigations rather
// than rebuilt per page. Bounded because chunks can be large; oldest entries go
// first, which keeps the much-reused metadata resident in practice.
const STORE_CACHE_BUDGET = 64 * 1024 * 1024;
const storeCache = new Map<string, Uint8Array>();
let storeCacheBytes = 0;

function cachePut(url: string, bytes: Uint8Array): void {
  if (storeCache.has(url)) return;
  storeCache.set(url, bytes);
  storeCacheBytes += bytes.byteLength;
  while (storeCacheBytes > STORE_CACHE_BUDGET) {
    const oldest = storeCache.keys().next();
    if (oldest.done) break;
    const evicted = storeCache.get(oldest.value);
    storeCache.delete(oldest.value);
    storeCacheBytes -= evicted?.byteLength ?? 0;
  }
}

// Integer IDS fields come back as BigInt64Array, which cannot be compared or
// mixed with numbers: a bare Math.min over one throws rather than returning
// something wrong. Everything downstream plots as floats, so narrow here.
function toFloatArray(data: unknown): Float32Array | Float64Array {
  if (data instanceof Float32Array || data instanceof Float64Array) return data;
  if (data instanceof BigInt64Array || data instanceof BigUint64Array) {
    const out = new Float64Array(data.length);
    for (let i = 0; i < data.length; i++) out[i] = Number(data[i]);
    return out;
  }
  return Float64Array.from(data as ArrayLike<number>);
}

// CF "units" attribute of an array in the group, if it declares one.
function unitsOf(items: Record<string, NodeMeta>, name: string | undefined): string | undefined {
  const units = name ? items[name]?.attributes?.units : undefined;
  return typeof units === "string" && units.trim() ? units : undefined;
}

function rowMajorStrides(shape: number[]): number[] {
  const stride = new Array(shape.length);
  stride[shape.length - 1] = 1;
  for (let d = shape.length - 2; d >= 0; d--) stride[d] = stride[d + 1] * shape[d + 1];
  return stride;
}

// Equilibrium reconstructions only cover part of the shot's time base, so the
// first slice of a field like psi is routinely all NaN: on shot 30420 the first
// 11 of 97 planes are empty. Opening on index 0 renders a blank square and reads
// as a broken viewer, so start at the first sample that actually holds data.
function defaultSliderIndices(
  data: Float32Array | Float64Array,
  shape: number[],
  sliders: { idx: number }[],
): number[] {
  if (sliders.length === 0) return [];
  let first = -1;
  for (let i = 0; i < data.length; i++) {
    if (Number.isFinite(data[i])) { first = i; break; }
  }
  if (first < 0) return sliders.map(() => 0);
  const stride = rowMajorStrides(shape);
  return sliders.map(s => Math.floor(first / stride[s.idx]) % shape[s.idx]);
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface LoadProgress {
  label: string;
  host: string;
  requests: number;
  bytes: number;
  cached: number;
}

interface NodeMeta {
  node_type?: string;
  attributes?: Record<string, unknown> & { name?: string; dimension_names?: string[] };
  shape?: number[];
  dimension_names?: string[];
  codecs?: { name: string }[];
  consolidated_metadata?: { metadata?: Record<string, NodeMeta> };
  members?: Record<string, NodeMeta>;
  [key: string]: unknown;
}

// Zarr node metadata for everything under one group, and where it came from.
interface GroupMetadata {
  // Node path relative to the group ("t_e", "time", ...) to its zarr.json content.
  nodes: Record<string, NodeMeta>;
  // Arrays and groups directly under the group, in listing order.
  items: Record<string, NodeMeta>;
}

// A store that consolidates at the root publishes one listing covering every
// group in it. Reading a single IDS group therefore means reading the shot's
// root listing and taking the slice under that group, which is one request for
// the whole shot instead of one per array, and is shared by every dataset on it.
function sliceConsolidated(rootMeta: NodeMeta, groupPrefix: string): GroupMetadata | null {
  const all = rootMeta?.consolidated_metadata?.metadata;
  if (!all) return null;
  const prefix = groupPrefix ? `${groupPrefix}/` : "";
  const nodes: Record<string, NodeMeta> = {};
  for (const [key, meta] of Object.entries(all as Record<string, NodeMeta>)) {
    if (!prefix || key.startsWith(prefix)) {
      nodes[prefix ? key.slice(prefix.length) : key] = meta;
    }
  }
  if (Object.keys(nodes).length === 0) return null;
  // Direct children only: the variable picker should not list nested groups' arrays.
  const items = Object.fromEntries(
    Object.entries(nodes).filter(([k]) => !k.includes("/"))
  );
  return { nodes, items };
}

// The enclosing "....zarr" store root, if the path is inside one.
function zarrRootOf(path: string): { root: string; group: string } | null {
  const parts = path.split("/");
  const idx = parts.findIndex((p) => p.endsWith(".zarr"));
  if (idx === -1 || idx === parts.length - 1) return null;
  return { root: parts.slice(0, idx + 1).join("/"), group: parts.slice(idx + 1).join("/") };
}

// Zarrita asks the store for each node's zarr.json and then for its chunks. Over
// a remote store those are the round trips that hurt, so this serves metadata
// from the listing already in hand and remembers every chunk it fetches. Chunks
// at a given path do not change, so the cache needs no invalidation.
function makeZarrStore(opts: {
  storeUrl: string;
  doFetch: (target: string) => Promise<Response>;
  nodes: Record<string, NodeMeta>;
  cache: Map<string, Uint8Array>;
  onHit: () => void;
  onFetched: (bytes: number) => void;
}) {
  const { storeUrl, doFetch, nodes, cache, onHit, onFetched } = opts;
  const encoder = new TextEncoder();
  return {
    async get(key: string): Promise<Uint8Array | undefined> {
      const cleanKey = key.replace(/^\//, "");

      if (cleanKey === "zarr.json" || cleanKey.endsWith("/zarr.json")) {
        const node = cleanKey.slice(0, -"zarr.json".length).replace(/\/$/, "");
        const meta = node === "" ? { zarr_format: 3, node_type: "group", attributes: {} } : nodes[node];
        if (meta) {
          onHit();
          return encoder.encode(JSON.stringify(meta));
        }
      }

      const url = `${storeUrl}/${cleanKey}`;
      const hit = cache.get(url);
      if (hit) {
        onHit();
        return hit;
      }

      const res = await doFetch(url);
      if (res.status === 404 || res.status === 403) return undefined;
      if (!res.ok) throw new Error(`Fetch failed: ${res.statusText}`);
      const bytes = new Uint8Array(await res.arrayBuffer());
      cache.set(url, bytes);
      onFetched(bytes.byteLength);
      return bytes;
    },
  };
}

function isHttp(url: string): boolean {
  return /^https?:\/\//.test(url);
}

function isIcechunk(d: Distribution): boolean {
  return d.storage_options_type === 'icechunk_s3' || Boolean(d.media_type?.toLowerCase().includes('icechunk'));
}

// "s3://bucket/some/prefix/" as its bucket and the key under it.
function splitS3(url: string): { bucket: string; key: string } {
  const rest = url.replace(/^s3:\/\//, '');
  const i = rest.indexOf('/');
  return i === -1
    ? { bucket: rest, key: '' }
    : { bucket: rest.slice(0, i), key: rest.slice(i + 1).replace(/\/$/, '') };
}

function fsspecOptions(access: DataAccess): string {
  // Public data in someone else's store needs no credentials at all, so the
  // snippet has to show anonymous access rather than empty credential fields.
  return access.anon
    ? `storage_options = {
    "anon": True,
    "client_kwargs": {"endpoint_url": "${access.endpointUrl}"},
}`
    : `storage_options = {
    "key": "${access.accessKeyId}",
    "secret": "${access.secretAccessKey}",
    "token": "${access.sessionToken}",
    "client_kwargs": {"endpoint_url": "${access.endpointUrl}"},
}`;
}

// An icechunk dataset is often a group in a larger store, the collection's
// root_url, so the store is opened there and the rest of the path is the group.
function icechunkSnippet(url: string, access: DataAccess, storeRoot?: string): string {
  const root = storeRoot && url.startsWith(storeRoot) ? storeRoot : url;
  const group = url.slice(root.length).replace(/^\/|\/$/g, '');
  const { bucket, key } = splitS3(root);
  const endpoint = new URL(access.endpointUrl);
  const onAws = endpoint.hostname === 'amazonaws.com' || endpoint.hostname.endsWith('.amazonaws.com');
  const args = [
    `bucket="${bucket}"`,
    `prefix="${key}"`,
    `endpoint_url="${access.endpointUrl}"`,
    // Without a region icechunk first asks the AWS instance metadata service,
    // which is not there off AWS and costs a timeout.
    `region="${access.region || 'us-east-1'}"`,
    ...(access.anon
      ? ['anonymous=True']
      : [
          `access_key_id="${access.accessKeyId}"`,
          `secret_access_key="${access.secretAccessKey}"`,
          `session_token="${access.sessionToken}"`,
        ]),
    ...(endpoint.protocol === 'http:' ? ['allow_http=True'] : []),
    // Any S3-compatible store other than AWS needs path-style addressing.
    ...(onAws ? [] : ['force_path_style=True']),
  ];
  return `# pip install icechunk xarray
import icechunk
import xarray as xr

storage = icechunk.s3_storage(
${args.map((a) => `    ${a},`).join('\n')}
)
repo = icechunk.Repository.open(storage)
session = repo.readonly_session("main")
ds = xr.open_zarr(session.store${group ? `, group="${group}"` : ''}, consolidated=False)
print(ds)`;
}

function buildSnippet(dist: Distribution, access: DataAccess, storeRoot?: string): string {
  const url = dist.url;
  const mediaType = (dist.media_type ?? '').toLowerCase();
  const format = (dist.format ?? '').toLowerCase();

  if (isIcechunk(dist)) return icechunkSnippet(url, access, storeRoot);

  const options = fsspecOptions(access);

  if (isZarr(mediaType)) {
    return `# pip install xarray zarr s3fs
import xarray as xr

${options}

ds = xr.open_zarr("${url}", storage_options=storage_options)
print(ds)`;
  }

  if (mediaType.includes('csv') || format.includes('csv')) {
    return `# pip install pandas s3fs
import pandas as pd

${options}

df = pd.read_csv("${url}", storage_options=storage_options)
print(df)`;
  }

  if (mediaType.includes('parquet') || format.includes('parquet')) {
    return `# pip install pandas s3fs
import pandas as pd

${options}

df = pd.read_parquet("${url}", storage_options=storage_options)
print(df)`;
  }

  if (/netcdf|hdf/.test(mediaType) || /netcdf|hdf/.test(format)) {
    // With s3fs's default 50 MB read-ahead, reading one group of a 397 MB
    // file fetched 839 MB.
    const open = dist.group
      ? `fs.open("${url}", block_size=4 * 2**20, cache_type="blockcache")`
      : `fs.open("${url}")`;
    return `# pip install xarray h5netcdf h5py s3fs
import s3fs
import xarray as xr

${options}

fs = s3fs.S3FileSystem(**storage_options)
ds = xr.open_dataset(${open}, engine="h5netcdf"${dist.group ? `, group="${dist.group}"` : ''})
print(ds)`;
  }

  return `# pip install s3fs
import s3fs

${options}

fs = s3fs.S3FileSystem(**storage_options)
data = fs.cat("${url}")  # ${dist.media_type || 'unknown format'}: open these bytes with a reader for it
`;
}

export default function DatasetDetail({ id, jsonLd }: { id: string; jsonLd?: JsonLd | null }) {

  const { status } = useSession();
  // Access is decided for the dataset as a whole, so one request covers every
  // distribution. byUrl says how to open each one FDS granted.
  const [accessValues, setAccessValues] = useState<{granted: boolean, byUrl: Record<string, DataAccess>, error?: string}>({ granted: false, byUrl: {} });
  const [selectedDistId, setSelectedDistId] = useState<number | null>(null);
  const [showGraph, setShowGraph] = useState(false);
  const [zarrMetadata, setZarrMetadata] = useState<NodeMeta | null>(null);
  const [showCodeModal, setShowCodeModal] = useState(false);
  const [variables, setVariables] = useState<string[]>([]);
  const [coordinates, setCoordinates] = useState<string[]>([]);
  const [selectedVar, setSelectedVar] = useState<string | null>(null);
  const [chunkData, setChunkData] = useState<{ data: Float32Array | Float64Array, shape: number[], x?: Float32Array | Float64Array, yAxis?: Float32Array | Float64Array, units?: { x?: string, y?: string, value?: string }, yL?: string, xL?: string, xIdx?: number, yIdx?: number, yAxisL?: string, sliders?: { name: string, data?: Float32Array | Float64Array, shapeSize: number, idx: number }[] } | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [sliderIndices, setSliderIndices] = useState<number[]>([]);
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Node metadata for the group, resolved once when the dataset is opened.
  const groupMeta = useRef<GroupMetadata | null>(null);

  const { data: datasetData } = useSWR<Dataset>(
    id
      ? `${API_BASE}/datasets/id/${id}?include_geometry=true&include_calibration=true&include_annotations=true`
      : null,
    fetcher
  );

  const { data: activityData } = useSWR<ActivityType>(
    datasetData?.activity_id ? `${API_BASE}/datasets/${datasetData.id}/activity` : null,
    fetcher
  );

  const { data: executor } = useSWR<Source>(
    activityData?.source_id != null ? `${API_BASE}/sources/id/${activityData.source_id}` : null,
    fetcher
  );

  // Default first, so it is what is selected and, when it is Zarr, what is plotted.
  const distributions = [...(datasetData?.distributions ?? [])].sort(
    (a, b) => Number(b.default_distribution) - Number(a.default_distribution)
  );
  const selectedDist = distributions.find((d) => d.id === selectedDistId) ?? distributions[0];
  const selectedAccess = selectedDist ? accessValues.byUrl[selectedDist.url] : undefined;
  // Distributions are interchangeable, so any Zarr one can be plotted, whichever
  // is selected.
  const vizDist = distributions.find(canVisualise);
  const vizAccess = vizDist ? accessValues.byUrl[vizDist.url] : undefined;

  const cite = datasetData ? citation(datasetData) : null;

  const device = datasetData?.device_name;
  const shot = datasetData?.shot_id;
  const deviceLabel = useDeviceLabel(device);

  // An icechunk dataset may be a group in its collection's store, whose root is
  // the collection's root_url.
  const { data: shotCollections } = useSWR<Collection[]>(
    selectedDist && isIcechunk(selectedDist) && device && shot
      ? `${API_BASE}/devices/${device}/shots/${shot}/collections`
      : null,
    fetcher
  );
  const storeRoot = (shotCollections ?? [])
    .map((c) => c.root_url)
    .filter((r): r is string => Boolean(r) && Boolean(selectedDist?.url.startsWith(r as string)))
    .sort((a, b) => b.length - a.length)[0];

  const handleRequestAccess = async () => {
      if (datasetData?.effective_access_level !== "public" && status !== "authenticated") {
          signIn("keycloak");
          return;
      }

      if (distributions.length === 0) {
          setAccessValues({ granted: false, byUrl: {}, error: "Dataset has no data URL." });
          return;
      }

      // Public data in an S3 store opens anonymously, with nothing to vend and
      // no round trip to make. This is the path a dataset held in another
      // organisation's public store takes.
      const isPublic = datasetData?.effective_access_level === 'public';
      const byUrl: Record<string, DataAccess> = {};
      const toVend: string[] = [];
      for (const d of distributions) {
          // An HTTPS download is opened by its URL, with nothing to grant.
          if (isHttp(d.url)) continue;
          if (isPublic) {
              byUrl[d.url] = {
                  endpointUrl: d.endpoint_url ?? MINIO_FALLBACK,
                  anon: true,
                  region: d.region ?? undefined,
              };
          } else {
              toVend.push(d.url);
          }
      }

      let error: string | undefined;
      if (toVend.length > 0) {
          try {
              const res = await fetch(`${API_BASE}/file-access/credentials`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data_urls: toVend })
              });

              if (!res.ok) throw new Error("Failed to get credentials");

              const manifest = await res.json();
              for (const url of toVend) {
                  const cred = manifest.resource_map[url];
                  if (!cred) continue;
                  byUrl[url] = {
                      endpointUrl: cred.endpoint_url ?? MINIO_FALLBACK,
                      anon: false,
                      accessKeyId: cred.access_key_id,
                      secretAccessKey: cred.secret_access_key,
                      sessionToken: cred.session_token,
                      region: cred.region,
                  };
              }
          } catch (e) {
              console.error(e);
              error = e instanceof Error ? e.message : String(e);
          }
      }

      if (toVend.length > 0 && Object.keys(byUrl).length === 0) {
          setAccessValues({ granted: false, byUrl: {}, error: error ?? "FDS issued no credentials for this dataset." });
          return;
      }
      setAccessValues({ granted: true, byUrl });
      if (vizDist && byUrl[vizDist.url]) loadZarrData(byUrl[vizDist.url], vizDist.url);
  };

  const [autoLoadAttempted, setAutoLoadAttempted] = useState(false);

  useEffect(() => {
      if (!showGraph && !showCodeModal) return;
      const onKey = (e: KeyboardEvent) => {
          if (e.key !== 'Escape') return;
          setShowGraph(false);
          setShowCodeModal(false);
      };
      window.addEventListener('keydown', onKey);
      return () => window.removeEventListener('keydown', onKey);
  }, [showGraph, showCodeModal]);

  useEffect(() => {
     if (datasetData && status !== "loading" && !autoLoadAttempted && !accessValues.granted && !accessValues.error) {
         // Public data opens without asking, so there is nothing to click for.
         if (datasetData.effective_access_level === 'public' || (vizDist && status === "authenticated")) {
             setAutoLoadAttempted(true);
             handleRequestAccess();
         }
     }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetData, status, autoLoadAttempted, accessValues.granted, accessValues.error]);

  const loadZarrData = async (access: DataAccess, s3Path: string) => {
      // s3Path is like "s3://mast/level2/shots/30421.zarr/equilibrium" for data in
      // a public store, or "s3://fds-data/shots/50000/analysed" for data the demo
      // holds itself. Which host serves it is FDS's answer, not ours to assume.
      const { origin, path: prefixPath } = objectUrl(access.endpointUrl, s3Path);
      // fetchVariables needs zarrita as soon as the metadata is in, so load it
      // alongside the metadata rather than after.
      import('zarrita').catch(() => {});
      const doFetch = await makeFetcher(access);
      const host = new URL(access.endpointUrl).host;
      setLoadError(null);
      setProgress({ label: "Reading dataset metadata", host, requests: 0, bytes: 0, cached: 0 });

      const countFetched = (n: number) =>
        setProgress(p => p ? { ...p, requests: p.requests + 1, bytes: p.bytes + n } : p);
      const countHit = () => setProgress(p => p ? { ...p, cached: p.cached + 1 } : p);

      const getJson = async (url: string) => {
        const cached = storeCache.get(url);
        if (cached) { countHit(); return JSON.parse(new TextDecoder().decode(cached)); }
        const res = await doFetch(url);
        if (!res.ok) return null;
        const bytes = new Uint8Array(await res.arrayBuffer());
        cachePut(url, bytes);
        countFetched(bytes.byteLength);
        return JSON.parse(new TextDecoder().decode(bytes));
      };

      try {
        // 1. Group metadata. A store that consolidates only at its root leaves
        //    each group's own zarr.json bare, so fall back to the root listing
        //    and take the slice for this group. The root listing is requested
        //    with the group's rather than after it, since waiting costs a round trip.
        const rootRef = zarrRootOf(prefixPath);
        const rootMetaRead = rootRef ? getJson(`${origin}/${rootRef.root}/zarr.json`) : null;
        // Never awaited when the group lists itself, so a failure must not
        // surface as an unhandled rejection.
        rootMetaRead?.catch(() => {});
        const metadata = await getJson(`${origin}/${prefixPath}/zarr.json`);
        if (metadata) {
           setZarrMetadata(metadata);

           let resolved = sliceConsolidated(metadata, "");
           if (!resolved && metadata.members) {
               resolved = { nodes: metadata.members, items: metadata.members };
           }
           if (!resolved && rootRef && rootMetaRead) {
               const rootMeta = await rootMetaRead;
               if (rootMeta) resolved = sliceConsolidated(rootMeta, rootRef.group);
           }
           groupMeta.current = resolved;
           const items: Record<string, NodeMeta> = resolved?.items ?? {};

           const arrayNames = Object.keys(items).filter(key =>
               items[key]?.node_type === 'array' || items[key]?.attributes?.name
           );

           const allDimNames = new Set<string>();
           // CF convention: a variable names its non-dimension coordinates in a
           // space-separated "coordinates" attribute. shot_id is one of these —
           // it labels the data rather than being data, so it is not plottable.
           const namedCoords = new Set<string>();
           arrayNames.forEach(k => {
               const dims = items[k].dimension_names || [];
               dims.forEach((d: string) => allDimNames.add(d));
               const declared = items[k].attributes?.coordinates;
               if (typeof declared === "string") {
                   declared.split(/\s+/).filter(Boolean).forEach((c: string) => namedCoords.add(c));
               }
           });

           const coords = arrayNames.filter(k =>
               allDimNames.has(k)
               || namedCoords.has(k)
               || (items[k].dimension_names?.length === 1 && items[k].dimension_names[0] === k)
           );
           setCoordinates(coords);

           const dataVars = arrayNames.filter(k => !coords.includes(k) && !k.includes("/"));

           setVariables(dataVars);
           if (dataVars.length > 0) {
               setSelectedVar(dataVars[0]);
               await fetchVariables(access, prefixPath, dataVars[0], coords, items);
               return;
           }
        } else {
           setLoadError(`No Zarr metadata at ${origin}/${prefixPath}`);
        }
      } catch (err) {
        console.error("Zarr fetch error:", err);
        setLoadError(
            `Could not read dataset metadata from ${host}: ${err instanceof Error ? err.message : String(err)}`
        );
      }
      setProgress(null);
  };

  const fetchVariables = async (access: DataAccess, prefixPath: string, varName: string, coordsList: string[], allItems: Record<string, NodeMeta>) => {
      setLoadingData(true);
      setLoadError(null);
      const host = new URL(access.endpointUrl).host;
      setProgress(p => ({
          label: `Reading ${varName}`,
          host,
          requests: p?.requests ?? 0,
          bytes: p?.bytes ?? 0,
          cached: p?.cached ?? 0,
      }));
      try {
          const zarr = await import('zarrita');
          const doFetch = await makeFetcher(access);

          const origin = new URL(access.endpointUrl).origin;
          const storeUrl = `${origin}/${prefixPath.replace(/\/$/, '')}`;

          const customStore = makeZarrStore({
              storeUrl,
              doFetch,
              nodes: groupMeta.current?.nodes ?? {},
              cache: storeCache,
              onHit: () => setProgress(p => p ? { ...p, cached: p.cached + 1 } : p),
              onFetched: (n) => setProgress(p => p ? { ...p, requests: p.requests + 1, bytes: p.bytes + n } : p),
          });

          const root = zarr.root(customStore);

          // The store is Zarr v3. zarr.open would look for v2 metadata first,
          // which is two requests per array that cannot succeed.
          const openArray = (name: string) => zarr.open.v3(root.resolve(name), { kind: "array" });
          const readCoordinate = async (name: string | undefined) => {
              if (!name || !coordsList.includes(name)) return undefined;
              return toFloatArray((await zarr.get(await openArray(name))).data);
          };

          const dataArr = await openArray(varName);

          // Coordinate Array Matching
          const dataAxisNames = allItems[varName]?.dimension_names || [];

          let xL: string | undefined;
          let yAxisL: string | undefined;
          let xIdx: number | undefined;
          let yIdx: number | undefined;
          let sliderDims: { name: string; i: number }[] = [];

          if (dataAxisNames.length === 1) {
              xL = dataAxisNames.find((d: string) => coordsList.includes(d));
              xIdx = 0;
          } else if (dataAxisNames.length >= 2) {
              const spatialIndices: number[] = [];
              for (let i = 0; i < dataAxisNames.length; i++) {
                  if (!dataAxisNames[i].toLowerCase().includes('time')) {
                      spatialIndices.push(i);
                  }
              }

              if (spatialIndices.length >= 2) {
                  xIdx = spatialIndices[spatialIndices.length - 1]; // Last spatial is X (e.g. radius)
                  yIdx = spatialIndices[spatialIndices.length - 2]; // 2nd to last is Y (e.g. z)
                  yAxisL = dataAxisNames[yIdx];
              } else if (spatialIndices.length === 1) {
                  xIdx = spatialIndices[0];
              } else {
                  xIdx = 0;
              }

              xL = dataAxisNames[xIdx];

              // One scalar slider per non-X, non-Y dimension.
              sliderDims = dataAxisNames
                  .map((name: string, i: number) => ({ name, i }))
                  .filter(({ i }: { i: number }) => i !== xIdx && i !== yIdx);
          }

          // zarrita imports a decompressor when it decodes the first chunk that
          // needs it, so the import would wait for that chunk to download.
          // Starting it now overlaps the two.
          new Set(
              [varName, xL, ...sliderDims.map(({ name }) => name)]
                  .flatMap((name) => (name && allItems[name]?.codecs) || [])
                  .map((codec) => codec.name)
          ).forEach((name) => Promise.resolve(zarr.registry.get(name)?.()).catch(() => {}));

          // The variable, its X and Y coordinates and every slider coordinate are
          // independent reads, so issue them as a single batch: over a remote
          // store this is the difference between one round trip and one per array.
          const [view, xData, yData, ...sliderData] = await Promise.all([
              zarr.get(dataArr),
              readCoordinate(xL),
              readCoordinate(yAxisL),
              ...sliderDims.map(({ name }) => readCoordinate(name)),
          ]);
          const viewData = toFloatArray(view.data);
          const sliders = sliderDims.map(({ name, i }, n) => ({
              name,
              data: sliderData[n],
              shapeSize: view.shape[i],
              idx: i,
          }));

          setChunkData({
              data: viewData,
              shape: view.shape,
              x: xData as Float32Array | Float64Array | undefined,
              yAxis: yData,
              units: {
                  x: unitsOf(allItems, xL),
                  y: unitsOf(allItems, yAxisL),
                  value: unitsOf(allItems, varName),
              },
              yL: varName,
              xL: xL,
              yAxisL,
              xIdx,
              yIdx,
              sliders
          });
          setSliderIndices(defaultSliderIndices(viewData, view.shape, sliders));
      } catch (err) {
          // A read from someone else's store fails for reasons the page cannot
          // control: the host throttles, goes down, or drops a chunk part-way.
          // Say so rather than leaving an empty panel that looks like no data.
          console.error("Zarrita chunk fetch error:", err);
          setLoadError(
              `Could not read ${varName} from ${host}: ${err instanceof Error ? err.message : String(err)}`
          );
      } finally {
         setLoadingData(false);
         setProgress(null);
      }
  };

  const onSelectVariable = async (newVar: string) => {
      setSelectedVar(newVar);
      if (!vizAccess || !vizDist) return;

      const { path: prefixPath } = objectUrl(vizAccess.endpointUrl, vizDist.url);

      // Use the metadata resolved when the dataset was opened. Re-deriving it from
      // the group's own zarr.json loses everything for a store that consolidates
      // only at its root, which leaves the variable with no dimensions and so no
      // axes and no sliders.
      const items = groupMeta.current?.items;
      if (!items) return;
      fetchVariables(vizAccess, prefixPath, newVar, coordinates, items);
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Code Snippet Modal */}
      {showCodeModal && selectedDist && selectedAccess && (
        <div onClick={() => setShowCodeModal(false)} className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div onClick={(e) => e.stopPropagation()} className="bg-card border border-border rounded-xl max-w-3xl w-full shadow-2xl relative overflow-hidden animate-fade-in">
              <div className="flex justify-between items-center bg-muted p-4 border-b border-border">
                  <h3 className="text-lg font-bold text-foreground flex items-center gap-2"><Activity className="w-5 h-5 text-primary"/> Open in Python</h3>
                  <button onClick={() => setShowCodeModal(false)} className="text-muted-foreground hover:text-foreground text-2xl leading-none">&times;</button>
              </div>
              <div className="p-6">
                  <p className="text-sm text-foreground mb-4">
                      {selectedAccess.anon
                        ? "This data is openly published, so it opens anonymously, straight from the store holding it."
                        : "The credentials below were issued to you and expire. Do not share them or commit them to version control."}
                  </p>
                  <div className="bg-background p-4 rounded-lg overflow-x-auto border border-border relative group">
                      {(() => {
                          const snippet = buildSnippet(selectedDist, selectedAccess, storeRoot);
                          return (
                              <>
                                  <button
                                      onClick={() => navigator.clipboard.writeText(snippet)}
                                      className="absolute top-2 right-2 bg-muted hover:bg-muted text-xs text-foreground px-3 py-1 rounded-sm opacity-0 group-hover:opacity-100 transition-opacity"
                                  >Copy Snippet</button>
                                  <pre className="text-foreground text-sm font-mono whitespace-pre-wrap">{snippet}</pre>
                              </>
                          );
                      })()}
                  </div>
              </div>
          </div>
        </div>
      )}

      {showGraph && datasetData?.id && (
        <div onClick={() => setShowGraph(false)} className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-xs">
          <div onClick={(e) => e.stopPropagation()} className="bg-card border border-border rounded-xl max-w-6xl w-full shadow-2xl relative overflow-hidden animate-fade-in">
              <div className="flex justify-between items-center bg-muted p-4 border-b border-border">
                  <h3 className="text-lg font-bold text-foreground flex items-center gap-2"><Activity className="w-5 h-5 text-primary"/> Provenance Graph</h3>
                  <button onClick={() => setShowGraph(false)} className="text-muted-foreground hover:text-foreground text-2xl leading-none">&times;</button>
              </div>
              <div className="p-6">
                  <ProvenanceGraph datasetId={datasetData.id} />
              </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="mb-8">
         <div className="flex items-center text-sm text-muted-foreground mb-6 font-medium">
            <Link href="/devices" className="hover:text-primary transition-colors flex items-center">Devices</Link>
            <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
            {device && (
              <>
                <Link href={`/devices/${device}`} className="hover:text-primary transition-colors flex items-center">{deviceLabel}</Link>
                <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
              </>
            )}
            {device && shot && (
              <>
                <Link href={`/devices/${device}/shots/${shot}`} className="hover:text-primary transition-colors flex items-center">Shot #{shot}</Link>
                <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
              </>
            )}
            <span className="text-foreground">{datasetData?.name || id}</span>
         </div>
         <h1 className="text-4xl font-bold flex items-center gap-3 mb-4">
            <Database className="text-primary w-8 h-8" />
            {datasetData?.name || id}
         </h1>
         {datasetData?.description && (
           <p className="text-lg text-foreground max-w-4xl leading-relaxed mb-6">
              {datasetData.description}
           </p>
         )}
         <div className="flex flex-wrap gap-3">
             {device && <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">Device: {deviceLabel}</span>}
             {shot && <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">Shot: {shot}</span>}
             {datasetData?.annotates && (
                <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border flex items-center gap-1">
                    <Highlighter className="w-3.5 h-3.5" />
                    Annotates: {datasetData.annotates}
                </span>
             )}
         </div>
      </div>

      <div className={datasetData && !vizDist ? 'max-w-3xl' : 'grid grid-cols-1 lg:grid-cols-3 gap-8'}>

        {/* Left Column: Metadata & Controls Sidebar */}
        <div className="space-y-6">

            <div className="card p-6 bg-card/60 shadow-xl border-border overflow-hidden">
                <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground">Dataset Properties</h3>
                <div className="space-y-3 text-sm">
                    {datasetData?.persistent_identifier && (() => {
                        const href = resolveIdentifier(datasetData.persistent_identifier);
                        return (
                            <Property label="Persistent identifier">
                                {href
                                    ? <a href={href} className="font-mono text-primary hover:text-foreground break-all">{href}</a>
                                    : <span className="font-mono text-foreground break-all">{datasetData.persistent_identifier}</span>}
                            </Property>
                        );
                    })()}
                    {datasetData?.creator && <Property label="Creator"><span className="text-foreground">{datasetData.creator}</span></Property>}
                    {datasetData?.issued && (
                        <Property label="Published">
                            {/* A calendar date: read as UTC so no timezone shifts it a day. */}
                            <span className="text-foreground">{new Date(datasetData.issued).toLocaleDateString(undefined, { ...DATE, timeZone: 'UTC' })}</span>
                        </Property>
                    )}
                    {datasetData?.license && (
                        <Property label="Licence">
                            {/^https?:\/\//.test(datasetData.license)
                                ? <a href={datasetData.license} className="text-primary hover:text-foreground break-all">{datasetData.license}</a>
                                : <span className="text-foreground">{datasetData.license}</span>}
                        </Property>
                    )}
                    <Property label="Access level">
                        <span className="text-foreground capitalize">{datasetData?.effective_access_level || datasetData?.access_level || 'Unknown'}</span>
                    </Property>
                    {activityData?.ended_at && (
                        <Property label="Generated">
                            <Link href={`/activities/${activityData.id}`} className="text-primary hover:text-foreground">
                                {new Date(activityData.ended_at).toLocaleString(undefined, INSTANT)}
                            </Link>
                        </Property>
                    )}
                    {datasetData?.version && <Property label="Version"><span className="text-foreground">{datasetData.version}</span></Property>}
                    {datasetData?.publisher && <Property label="Publisher"><span className="text-foreground">{datasetData.publisher}</span></Property>}
                    {(datasetData?.temporal_start || datasetData?.temporal_end) && (
                        <Property label="Temporal coverage">
                            <span className="text-foreground">
                                {datasetData.temporal_start ? new Date(datasetData.temporal_start).toLocaleString(undefined, INSTANT) : 'unknown'}
                                {' to '}
                                {datasetData.temporal_end ? new Date(datasetData.temporal_end).toLocaleString(undefined, INSTANT) : 'unknown'}
                            </span>
                        </Property>
                    )}
                    {datasetData?.keywords && (
                        <Property label="Keywords">
                            <span className="flex flex-wrap gap-1.5">
                                {datasetData.keywords.split(',').map((k) => k.trim()).filter(Boolean).map((k) => (
                                    <span key={k} className="text-xs bg-muted border border-border rounded-full px-2 py-0.5 text-foreground">{k}</span>
                                ))}
                            </span>
                        </Property>
                    )}
                    {datasetData?.quality_flag && <Property label="Quality"><span className="text-foreground">{datasetData.quality_flag}</span></Property>}
                    <Property label="Listed in FDS" last>
                        <span className="text-foreground">{datasetData?.created_at ? new Date(datasetData.created_at).toLocaleDateString(undefined, DATE) : 'Unknown'}</span>
                    </Property>
                </div>
                <JsonLdPanel url={`${API_BASE}/datasets/id/${id}`} document={jsonLd} className="-mx-6 -mb-6 mt-4 border-t border-border px-2 py-1.5" />
            </div>

            <div className="card p-6 bg-muted/80 shadow-xl border-border">
                <h3 className="text-lg font-bold mb-4 flex items-center justify-between text-foreground">
                    Data Access
                    {selectedAccess || (selectedDist && isHttp(selectedDist.url)) ? <Unlock className="w-5 h-5 text-foreground" /> : <Lock className="w-5 h-5 text-muted-foreground" />}
                </h3>

                {distributions.length > 1 && (
                    <div className="mb-6">
                        <p className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-2">
                            Distributions ({distributions.length})
                        </p>
                        <div className="space-y-1" role="radiogroup" aria-label="Distribution">
                            {distributions.map((d) => {
                                const selected = d.id === selectedDist?.id;
                                return (
                                    <button
                                        key={d.id}
                                        role="radio"
                                        aria-checked={selected}
                                        onClick={() => setSelectedDistId(d.id)}
                                        className={`w-full text-left px-3 py-2 rounded-sm border text-sm flex items-center gap-2 transition-colors ${selected ? 'border-primary bg-card' : 'border-border hover:bg-card/60'}`}
                                    >
                                        <span className={`w-3 h-3 shrink-0 rounded-full border ${selected ? 'border-primary bg-primary' : 'border-muted-foreground'}`} />
                                        <span className="flex-1 min-w-0">
                                            <span className="block text-foreground truncate">{distributionLabel(d)}</span>
                                            {d.format && d.media_type && (
                                                <span className="block text-xs text-muted-foreground font-mono truncate">{d.media_type}</span>
                                            )}
                                        </span>
                                        {d.default_distribution && (
                                            <span className="text-[10px] uppercase tracking-wider text-muted-foreground border border-border rounded-sm px-1">Default</span>
                                        )}
                                        {d.id === vizDist?.id && (
                                            <span className="text-[10px] uppercase tracking-wider text-primary border border-primary/50 rounded-sm px-1">Plotted</span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {distributions.length === 1 && selectedDist && (
                    <div className="space-y-1 text-xs mb-4">
                        <p className="text-muted-foreground font-medium uppercase tracking-wider">Format</p>
                        <p className="text-sm text-foreground">
                            {distributionLabel(selectedDist)}
                            {selectedDist.format && selectedDist.media_type && (
                                <span className="text-xs text-muted-foreground font-mono ml-2">{selectedDist.media_type}</span>
                            )}
                        </p>
                    </div>
                )}

                {selectedDist && (
                    <div className="space-y-2 text-xs">
                        <p className="text-muted-foreground font-medium uppercase tracking-wider">URI</p>
                        <p className="break-all text-foreground font-mono bg-card border border-border p-2 rounded-sm">{selectedDist.url}</p>
                        {selectedDist.group && (
                            <>
                                <p className="text-muted-foreground font-medium uppercase tracking-wider pt-1">Group</p>
                                <p className="break-all text-foreground font-mono bg-card border border-border p-2 rounded-sm">{selectedDist.group}</p>
                            </>
                        )}
                    </div>
                )}

                {selectedDist && isHttp(selectedDist.url) ? (
                    <a href={selectedDist.url} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:text-foreground inline-flex items-center gap-1 mt-3">
                        <Download className="w-4 h-4" /> Download
                    </a>
                ) : selectedAccess ? (
                    <button onClick={() => setShowCodeModal(true)} className="text-sm text-primary hover:text-foreground inline-flex items-center gap-1 mt-3">
                        <Download className="w-4 h-4" /> Open in Python
                    </button>
                ) : accessValues.granted ? (
                    <p className="text-sm text-muted-foreground mt-3">FDS issued no credentials for this distribution.</p>
                ) : selectedDist && datasetData?.effective_access_level !== 'public' ? (
                    <div className="mt-4">
                        <p className="text-muted-foreground text-sm mb-4 leading-relaxed">
                            This data is restricted. Sign in with an account that has access, and FDS issues you temporary credentials for reading it.
                        </p>
                        {accessValues.error && <p className="text-destructive mb-4 text-sm bg-destructive/10 p-2 rounded-sm border border-destructive/40">{accessValues.error}</p>}
                        <button
                            onClick={handleRequestAccess}
                            className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold py-3 px-4 rounded-sm w-full transition-colors flex items-center justify-center gap-2 shadow-lg hover:shadow-primary/25"
                        >
                            <Unlock className="w-4 h-4" />
                            {status === "authenticated" ? "Get access" : "Sign in to access"}
                        </button>
                    </div>
                ) : null}
            </div>

            {/* Annotations on this dataset's own axes */}
            <ScientificMetadata properties={datasetData?.scientific_metadata} className="bg-card/60 shadow-xl border-border" />

            {/* Datasets resolved for this one. The annotations are those whose
                subject is this dataset — the shot's are resolved on the shot,
                on its axes, and deliberately not folded in here. */}
            {((datasetData?.geometry?.length ?? 0) > 0 || (datasetData?.calibration?.length ?? 0) > 0 || (datasetData?.annotations?.length ?? 0) > 0) && (
                <div className="card p-6 bg-card/60 shadow-xl border-border">
                    <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground">Related Data</h3>
                    <div className="space-y-4 text-sm">
                        <RelatedGroup icon={MapPin} label="Geometry" datasets={datasetData?.geometry} />
                        <RelatedGroup
                            icon={SlidersHorizontal}
                            label="Calibration"
                            hint="— applied in order"
                            datasets={datasetData?.calibration}
                        />
                        <RelatedGroup
                            icon={Highlighter}
                            label="Annotations"
                            hint="— on this dataset's axes"
                            datasets={datasetData?.annotations}
                        />
                    </div>
                </div>
            )}

            {/* Provenance Card */}
            <div className="card p-6 bg-card/60 shadow-xl border-border">
                <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
                    <Activity className="w-5 h-5 text-muted-foreground" /> Provenance
                </h3>
                {activityData ? (
                    <div className="space-y-3 text-sm">
                        {activityData.activity_type && (
                            <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                                <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Activity Type</span>
                                <span className="text-foreground">{activityData.activity_type}</span>
                            </div>
                        )}
                        {activityData.source_version && (
                            <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                                <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Source Version</span>
                                <TruncatedValue value={activityData.source_version} />
                            </div>
                        )}
                        {activityData.started_at && (
                            <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                                <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Started</span>
                                <span className="text-foreground">{new Date(activityData.started_at).toLocaleString()}</span>
                            </div>
                        )}
                        {activityData.ended_at && (
                            <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                                <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Ended</span>
                                <span className="text-foreground">{new Date(activityData.ended_at).toLocaleString()}</span>
                            </div>
                        )}
                        {activityData.parameters && Object.keys(activityData.parameters).length > 0 && (
                            <div className="flex flex-col justify-start py-1">
                                <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Parameters</span>
                                <pre className="text-xs text-foreground font-mono bg-background border border-border p-2 rounded-sm overflow-x-auto">
                                    {JSON.stringify(activityData.parameters, null, 2)}
                                </pre>
                            </div>
                        )}
                        {executor && (
                            <Link
                                href={`/sources/${executor.id}`}
                                className="text-xs text-primary hover:text-foreground flex items-center gap-1 mt-2 transition-colors"
                            >
                                Source: {executor.name} <ChevronRight className="w-3 h-3" />
                            </Link>
                        )}
                        <Link
                            href={`/activities/${activityData.id}`}
                            className="text-xs text-primary hover:text-foreground flex items-center gap-1 transition-colors"
                        >
                            View activity <ChevronRight className="w-3 h-3" />
                        </Link>
                        {datasetData?.id && (
                            <button
                                onClick={() => setShowGraph(true)}
                                className="text-xs text-primary hover:text-foreground flex items-center gap-1 transition-colors"
                            >
                                Show provenance graph <ChevronRight className="w-3 h-3" />
                            </button>
                        )}
                    </div>
                ) : datasetData?.activity_id ? (
                    <p className="text-muted-foreground text-sm">Loading provenance...</p>
                ) : (
                    <div className="text-center py-4 bg-card/30 rounded-lg border border-dashed border-border">
                        <p className="text-xs text-muted-foreground">No provenance recorded for this dataset.</p>
                    </div>
                )}
            </div>

            {cite && (
                <div className="card p-6 bg-card/60 shadow-xl border-border">
                    <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center justify-between">
                        Cite this dataset
                        <CopyButton value={cite} />
                    </h3>
                    <p className="text-sm text-foreground leading-relaxed break-words">{cite}</p>
                </div>
            )}

        </div>

        {/* Right Column: Zarr Visualizer (only rendered when a distribution is Zarr) */}
        {(!datasetData || vizDist) && (
          // Sticky, so it stays in view beside a metadata column taller than it.
          <div className="lg:col-span-2 lg:sticky lg:top-20 self-start">
            <div className="card h-[650px] flex flex-col relative overflow-hidden shadow-2xl shadow-black/50 border border-border">
                <div className="absolute inset-0 bg-background/80 z-0">
                    {/* Grid Background Pattern */}
                    <div className="h-full w-full opacity-30" style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.2) 1px, transparent 1px)', backgroundSize: '30px 30px' }}></div>
                </div>

                <div className="relative z-10 p-4 flex justify-between items-center border-b border-border bg-card/90 backdrop-blur-sm">
                    <h3 className="font-mono text-sm text-foreground flex items-center gap-2 font-bold tracking-wider">
                        <Activity className="w-4 h-4" /> INTERACTIVE ZARR VISUALIZER
                    </h3>
                    <div className="flex gap-2">
                        {variables.length > 0 && (
                            <span className="text-xs bg-muted border border-border px-2 py-1 rounded-sm text-foreground">{variables.length} array variables</span>
                        )}
                    </div>
                </div>

                <div className="flex-1 flex items-center justify-center relative z-10">
                    {!vizAccess ? (
                        <div className="text-center p-8 bg-card/50 backdrop-blur-sm border border-border rounded-lg max-w-md">
                            <Lock className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                            <h4 className="text-lg font-bold text-foreground mb-2">Data Locked</h4>
                            <p className="text-muted-foreground text-sm mb-6">Sign in with an account that has access to plot this data in your browser.</p>
                            <button
                                onClick={handleRequestAccess}
                                className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold py-2 px-6 rounded-sm transition-colors flex items-center justify-center gap-2 mx-auto"
                            >
                                <Unlock className="w-4 h-4" />
                                {status === "authenticated" ? "Get access" : "Sign in"}
                            </button>
                        </div>
                    ) : (
                        <div className="w-full h-full flex flex-col items-start justify-start p-0">
                            {/* Visualizer Toolbar */}
                            <div className="w-full bg-card/80 border-b border-border p-4 flex gap-4 items-center backdrop-blur-sm">
                                <span className="text-sm font-medium text-muted-foreground">Variable:</span>
                                {variables.length > 0 ? (
                                    <select
                                        className="bg-background border border-border text-foreground text-sm rounded-sm focus:ring-primary focus:border-primary block p-2 shadow-inner min-w-[200px]"
                                        value={selectedVar || ''}
                                        onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                                           onSelectVariable(e.target.value);
                                        }}
                                    >
                                        {variables.map((v: string) => <option key={v} value={v}>{v}</option>)}
                                    </select>
                                ) : (
                                    <span className="text-sm text-muted-foreground italic">Scanning matrix...</span>
                                )}
                            </div>

                            <div className="flex-1 w-full p-6 relative flex items-center justify-center">
                                {loadError ? (
                                    <div className="flex flex-col items-center bg-card/50 p-6 rounded-lg backdrop-blur-sm max-w-md text-center">
                                        <Lock className="w-8 h-8 text-destructive mb-4" />
                                        <p className="text-sm text-foreground font-medium">Could not read the data</p>
                                        <p className="text-xs text-muted-foreground mt-2 break-words">{loadError}</p>
                                        <p className="text-[11px] text-muted-foreground mt-3">
                                            The metadata above comes from FDS; the data itself is served by the store holding it, which may be unreachable or rate-limiting.
                                        </p>
                                    </div>
                                ) : loadingData || progress ? (
                                    <div className="flex flex-col items-center bg-card/50 p-6 rounded-lg backdrop-blur-sm min-w-[18rem]">
                                        <Activity className="w-8 h-8 text-primary animate-spin mb-4" />
                                        <p className="text-sm text-foreground font-medium">
                                            {progress?.label ?? "Reading data"}
                                        </p>
                                        {progress && (
                                          <>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                streaming from <span className="font-mono">{progress.host}</span>
                                            </p>
                                            <div className="w-full h-1 bg-muted rounded-sm overflow-hidden mt-3">
                                                <div className="h-full w-1/3 bg-primary animate-indeterminate" />
                                            </div>
                                            <p className="text-[11px] text-muted-foreground mt-2 font-mono">
                                                {progress.requests} request{progress.requests === 1 ? "" : "s"}
                                                {" · "}{formatBytes(progress.bytes)}
                                                {progress.cached > 0 && ` · ${progress.cached} cached`}
                                            </p>
                                          </>
                                        )}
                                    </div>
                                ) : chunkData ? (
                                    <div className="w-full h-full flex flex-col items-center animate-fade-in relative z-10">
                                        {chunkData.sliders && chunkData.sliders.map((slider, i) => (
                                            <div key={slider.name} className="w-full max-w-3xl bg-card border border-border p-3 rounded-sm mb-2 flex gap-4 items-center shadow-lg">
                                                <span className="text-xs font-bold text-muted-foreground min-w-[120px] uppercase tracking-wider">
                                                    {slider.name}:
                                                    <span className="text-foreground ml-2 font-mono text-sm">
                                                        {slider.data && slider.data[sliderIndices[i] || 0] !== undefined
                                                            ? slider.data[sliderIndices[i] || 0].toFixed(4)
                                                            : (sliderIndices[i] || 0)}
                                                    </span>
                                                </span>
                                                <input
                                                    type="range"
                                                    className="flex-1 cursor-pointer accent-primary"
                                                    min="0"
                                                    max={slider.shapeSize - 1}
                                                    value={sliderIndices[i] || 0}
                                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                                                        const newIndices = [...sliderIndices];
                                                        newIndices[i] = Number(e.target.value);
                                                        setSliderIndices(newIndices);
                                                    }}
                                                />
                                            </div>
                                        ))}
                                        <div className="w-full flex-1 flex flex-col items-center justify-center mt-4">
                                            {(() => {
                                                const shape = chunkData.shape;
                                                const n = shape.length;

                                                if (n === 0) {
                                                    // A 0-d field such as shot_id. There is nothing to plot
                                                    // against, so show the value rather than an empty axis.
                                                    return (
                                                        <div className="flex flex-col items-center justify-center">
                                                            <p className="text-4xl font-mono text-foreground">
                                                                {Number.isFinite(chunkData.data[0]) ? chunkData.data[0] : "—"}
                                                            </p>
                                                            <p className="text-xs text-muted-foreground mt-4 bg-card px-3 py-1 rounded-sm font-mono">
                                                                {chunkData.yL} (scalar)
                                                            </p>
                                                        </div>
                                                    );
                                                }

                                                if (chunkData.yIdx !== undefined && chunkData.xIdx !== undefined) {
                                                    // === 2D HEATMAP CANVAS RENDERER ===
                                                    const xIdx = chunkData.xIdx;
                                                    const yIdx = chunkData.yIdx;
                                                    const height = shape[yIdx];
                                                    const width = shape[xIdx];

                                                    const strides = new Array(n);
                                                    strides[n-1] = 1;
                                                    for (let d = n - 2; d >= 0; d--) {
                                                        strides[d] = strides[d+1] * shape[d+1];
                                                    }

                                                    let baseOffset = 0;
                                                    chunkData.sliders?.forEach((slider, i) => {
                                                        baseOffset += (sliderIndices[i] || 0) * strides[slider.idx];
                                                    });

                                                    const data2D = new Float32Array(width * height);
                                                    let ptr = 0;
                                                    for (let y = 0; y < height; y++) {
                                                        const yOffset = baseOffset + y * strides[yIdx];
                                                        for (let x = 0; x < width; x++) {
                                                            data2D[ptr++] = chunkData.data[yOffset + x * strides[xIdx]];
                                                        }
                                                    }
                                                    return (
                                                        <HeatmapCanvas
                                                            data={data2D}
                                                            width={width}
                                                            height={height}
                                                            x={{ label: chunkData.xL ?? 'x', units: chunkData.units?.x, coords: chunkData.x }}
                                                            y={{ label: chunkData.yAxisL ?? 'y', units: chunkData.units?.y, coords: chunkData.yAxis }}
                                                            value={{ label: chunkData.yL ?? '', units: chunkData.units?.value }}
                                                            title={`${chunkData.yL} vs ${chunkData.xL} & ${chunkData.yAxisL}`}
                                                        />
                                                    );
                                                } else {
                                                    // === 1D SVG LINE RENDERER ===
                                                    let yData;
                                                    if (shape.length === 1) {
                                                        yData = chunkData.data;
                                                    } else if (shape.length >= 2 && chunkData.sliders && chunkData.xIdx !== undefined) {
                                                        const xIdx = chunkData.xIdx;

                                                        const strides = new Array(n);
                                                        strides[n-1] = 1;
                                                        for (let d = n - 2; d >= 0; d--) {
                                                            strides[d] = strides[d+1] * shape[d+1];
                                                        }

                                                        let baseOffset = 0;
                                                        chunkData.sliders.forEach((slider, i) => {
                                                            baseOffset += (sliderIndices[i] || 0) * strides[slider.idx];
                                                        });

                                                        const targetStride = strides[xIdx];
                                                        const targetSize = shape[xIdx];
                                                        yData = new Float32Array(targetSize);

                                                        if (targetStride === 1) {
                                                            yData = chunkData.data.subarray(baseOffset, baseOffset + targetSize);
                                                        } else {
                                                            for (let k = 0; k < targetSize; k++) {
                                                                yData[k] = chunkData.data[baseOffset + k * targetStride];
                                                            }
                                                        }
                                                    } else {
                                                        yData = chunkData.data;
                                                    }

                                                    const xData = chunkData.x;
                                                    // Decimate across the whole series rather than drawing its first
                                                    // 200 samples, which showed only the opening fraction of the axis.
                                                    const step = Math.max(1, Math.ceil(yData.length / 200));
                                                    const sampled: number[] = [];
                                                    for (let i = 0; i < yData.length; i += step) sampled.push(i);

                                                    // Normalise y to the viewBox from the data's own range —
                                                    // signals span many orders of magnitude (ip runs to ~1e5 A),
                                                    // so a fixed scale puts most traces off-canvas.
                                                    let minY = Infinity;
                                                    let maxY = -Infinity;
                                                    for (const i of sampled) {
                                                        const val = yData[i];
                                                        if (Number.isNaN(val)) continue;
                                                        if (val < minY) minY = val;
                                                        if (val > maxY) maxY = val;
                                                    }
                                                    if (!Number.isFinite(minY) || minY === maxY) { minY = (minY || 0) - 1; maxY = (maxY || 0) + 1; }
                                                    const scaleY = 160 / (maxY - minY);
                                                    const projectY = (val: number) => 180 - (Number.isNaN(val) ? 0 : val - minY) * scaleY;

                                                    let pathD: string;
                                                    if (xData && xData.length >= yData.length) {
                                                        const minX = Math.min(...sampled.map((i) => xData[i]));
                                                        const maxX = Math.max(...sampled.map((i) => xData[i]));
                                                        const scaleX = 400 / (maxX - minX || 1);

                                                        pathD = sampled.map((i, n) =>
                                                            `${n === 0 ? 'M' : 'L'}${(xData[i] - minX) * scaleX},${projectY(yData[i])}`
                                                        ).join(' ');
                                                    } else {
                                                        pathD = sampled.map((i, n) =>
                                                            `${n === 0 ? 'M' : 'L'}${(n / sampled.length) * 400},${projectY(yData[i])}`
                                                        ).join(' ');
                                                    }

                                                    const zeroY = projectY(0);
                                                    return (
                                                        <div className="w-full max-w-2xl h-full flex flex-col items-center justify-center p-4 bg-card/50 rounded-lg border border-border shadow-inner">
                                                            <svg viewBox="0 0 400 200" className="w-full flex-1 text-primary drop-shadow-[0_0_10px_rgba(59,130,246,0.6)]">
                                                                <path d={pathD} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
                                                                {minY <= 0 && maxY >= 0 && (
                                                                    <line x1="0" y1={zeroY} x2="400" y2={zeroY} stroke="#334155" strokeWidth="1" strokeDasharray="4 4" />
                                                                )}
                                                            </svg>
                                                            <p className="text-xs text-muted-foreground mt-4 bg-card px-3 py-1 rounded-full border border-border shadow-sm flex items-center gap-2 font-mono">
                                                                Plot: <span className="text-foreground font-bold">{chunkData.yL}</span> {chunkData.xL ? `vs ${chunkData.xL}` : ''} <span className="text-muted-foreground">({chunkData.shape[chunkData.xIdx !== undefined ? chunkData.xIdx : 0]} pts)</span>
                                                            </p>
                                                        </div>
                                                    );
                                                }
                                            })()}
                                        </div>
                                    </div>
                                ) : zarrMetadata ? (
                                     <div className="text-left w-full h-full overflow-auto pointer-events-auto p-4 bg-card/50 rounded-lg">
                                        <h4 className="font-bold text-foreground mb-2 border-b border-border pb-2">Zarr Array Mounted</h4>
                                        <p className="text-muted-foreground text-sm mb-4">Please select a variable from the dropdown above to begin visualization.</p>
                                     </div>
                                ) : null}
                            </div>
                        </div>
                    )}
                </div>
            </div>
          </div>
        )}

      </div>

    </div>
  );
}
