'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { Database, Lock, Unlock, Download, Activity, ChevronRight, MapPin, SlidersHorizontal, Highlighter } from 'lucide-react';
import { useSession, signIn } from "next-auth/react";
import useSWR from 'swr';
import { fetcher, API_BASE } from '@/lib/api';
import { Activity as ActivityType, Dataset } from '@/lib/types';
import ProvenanceGraph from '@/components/ProvenanceGraph';
import { ScientificMetadata } from '@/components/features';
import { RelatedGroup } from '@/components/related-data';
import { useDeviceLabel } from '@/lib/use-device-label';

// Heatmap Color Scale Approximation (Viridis)
const VIRIDIS_STOPS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [93, 201, 99], [253, 231, 37]];
function getViridisColor(t: number) {
    t = Math.max(0, Math.min(1, Number.isNaN(t) ? 0 : t));
    const idx = Math.floor(t * 4);
    if (idx >= 4) return VIRIDIS_STOPS[4];
    const frac = (t * 4) - idx;
    const c1 = VIRIDIS_STOPS[idx], c2 = VIRIDIS_STOPS[idx + 1];
    return [
       c1[0] + frac * (c2[0] - c1[0]),
       c1[1] + frac * (c2[1] - c1[1]),
       c1[2] + frac * (c2[2] - c1[2])
    ];
}

interface HeatmapProps {
    data: Float32Array | Float64Array;
    width: number;
    height: number;
    title: string;
}

function HeatmapCanvas({ data, width, height, title }: HeatmapProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    // A slice outside the reconstruction window is entirely NaN. Normalising it
    // yields NaN everywhere, which paints a uniform square that looks like data.
    // Say the slice is empty instead.
    let hasData = false;
    for (let i = 0; i < data.length; i++) {
        if (Number.isFinite(data[i])) { hasData = true; break; }
    }

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let min = Infinity, max = -Infinity;
        for (let i = 0; i < data.length; i++) {
            if (Number.isFinite(data[i])) {
                if (data[i] < min) min = data[i];
                if (data[i] > max) max = data[i];
            }
        }
        if (!Number.isFinite(min) || min === max) { min = (min || 0) - 1; max = (max || 0) + 1; }

        const imgData = ctx.createImageData(width, height);
        for (let i = 0; i < data.length; i++) {
            const x = i % width;
            const y = height - 1 - Math.floor(i / width); // Invert Y logically for physics
            const pixelIdx = (y * width + x) * 4;

            const normalized = (data[i] - min) / (max - min);
            const rgb = getViridisColor(normalized);
            imgData.data[pixelIdx] = rgb[0];
            imgData.data[pixelIdx + 1] = rgb[1];
            imgData.data[pixelIdx + 2] = rgb[2];
            imgData.data[pixelIdx + 3] = 255;
        }
        ctx.putImageData(imgData, 0, 0);
    }, [data, width, height]);

    return (
        <div className="w-full flex flex-col items-center justify-center p-2">
             {hasData ? (
                <canvas
                   ref={canvasRef}
                   width={width}
                   height={height}
                   className="w-full max-w-[300px] aspect-square object-contain pixelated border border-border bg-black/50"
                   style={{ imageRendering: 'pixelated' }}
                />
             ) : (
                <div className="w-full max-w-[300px] aspect-square border border-border border-dashed rounded flex items-center justify-center p-4">
                    <p className="text-xs text-muted-foreground text-center">
                        No data at this index.<br />Move the slider into the reconstruction window.
                    </p>
                </div>
             )}
             <p className="text-xs text-muted-foreground mt-4 bg-card px-3 py-1 rounded inline-flex font-mono">
                 Heatmap: {title}
             </p>
        </div>
    );
}

function isZarr(mediaType?: string | null): boolean {
  return Boolean(mediaType?.toLowerCase().includes('zarr'));
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

function buildSnippet(
  mediaType: string | null | undefined,
  access: DataAccess,
  s3Path: string,
): string {
  // Public data in someone else's store needs no credentials at all, so the
  // snippet has to show anonymous access rather than empty credential fields.
  const storageOptions = access.anon
    ? `storage_options = {
    "anon": True,
    "client_kwargs": {
        "endpoint_url": "${access.endpointUrl}"
    }
}`
    : `storage_options = {
    "key": "${access.accessKeyId}",
    "secret": "${access.secretAccessKey}",
    "token": "${access.sessionToken}",
    "client_kwargs": {
        "endpoint_url": "${access.endpointUrl}"
    }
}`;

  if (isZarr(mediaType)) {
    return `import xarray as xr

${storageOptions}

ds = xr.open_zarr("${s3Path}", storage_options=storage_options)
print(ds)`;
  }

  // NetCDF / HDF5: fs.cat + BytesIO avoids the HeadObject call that
  // xr.open_dataset(s3_url, ...) makes, our STS session policy grants
  // s3:GetObject only.
  return `import io

import s3fs
import xarray as xr

${storageOptions}

fs = s3fs.S3FileSystem(**storage_options)
data = fs.cat("${s3Path}")
ds = xr.open_dataset(io.BytesIO(data), engine="h5netcdf")
print(ds)`;
}

export default function DatasetDetail({ id }: { id: string }) {

  const { status } = useSession();
  const [accessValues, setAccessValues] = useState<{granted: boolean, token?: DataAccess, s3Path?: string, error?: string}>({ granted: false });
  const [zarrMetadata, setZarrMetadata] = useState<NodeMeta | null>(null);
  const [showCodeModal, setShowCodeModal] = useState(false);
  const [variables, setVariables] = useState<string[]>([]);
  const [coordinates, setCoordinates] = useState<string[]>([]);
  const [selectedVar, setSelectedVar] = useState<string | null>(null);
  const [chunkData, setChunkData] = useState<{ data: Float32Array | Float64Array, shape: number[], x?: Float32Array | Float64Array, yL?: string, xL?: string, xIdx?: number, yIdx?: number, yAxisL?: string, sliders?: { name: string, data?: Float32Array | Float64Array, shapeSize: number, idx: number }[] } | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [sliderIndices, setSliderIndices] = useState<number[]>([]);
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Node metadata for the group, resolved once when the dataset is opened.
  const groupMeta = useRef<GroupMetadata | null>(null);

  const { data: datasetData } = useSWR<Dataset>(
    id
      ? `${API_BASE}/datasets/id/${id}?include_geometry=true&include_calibration=true&include_annotations=true&include_storage_options=true`
      : null,
    fetcher
  );

  const { data: activityData } = useSWR<ActivityType>(
    datasetData?.activity_id ? `${API_BASE}/datasets/${datasetData.id}/activity` : null,
    fetcher
  );

  const device = datasetData?.device_name;
  const shot = datasetData?.shot_id;
  const deviceLabel = useDeviceLabel(device);

  const handleRequestAccess = async () => {
      if (datasetData?.effective_access_level !== "public" && status !== "authenticated") {
          signIn("keycloak");
          return;
      }

      const s3Path = datasetData?.url;
      if (!s3Path) {
          setAccessValues({ granted: false, error: "Dataset has no data URL." });
          return;
      }

      // Public data carries its own anonymous storage options, so there is
      // nothing to vend and no round trip to make. This is the path a dataset
      // held in another organisation's public store takes.
      const publicOpts = datasetData?.storage_options;
      if (datasetData?.effective_access_level === 'public' && publicOpts?.anon) {
          const access: DataAccess = {
              endpointUrl: publicOpts.client_kwargs?.endpoint_url ?? MINIO_FALLBACK,
              anon: true,
              region: publicOpts.client_kwargs?.region_name,
          };
          setAccessValues({ granted: true, token: access, s3Path });
          loadZarrData(access, s3Path);
          return;
      }

      try {
          const res = await fetch(`${API_BASE}/file-access/credentials`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_name: device, shot_id: shot })
          });

          if (!res.ok) throw new Error("Failed to get credentials");

          const manifest = await res.json();

          // resource_map maps URL → credential directly
          const validCreds = manifest.resource_map[s3Path] ?? null;

          if (validCreds) {
             const access: DataAccess = {
                 endpointUrl: validCreds.endpoint_url ?? MINIO_FALLBACK,
                 anon: false,
                 accessKeyId: validCreds.access_key_id,
                 secretAccessKey: validCreds.secret_access_key,
                 sessionToken: validCreds.session_token,
                 region: validCreds.region,
             };
             setAccessValues({ granted: true, token: access, s3Path });
             loadZarrData(access, s3Path);
          } else {
             setAccessValues({ granted: false, error: "No valid token retrieved for this dataset." });
          }

      } catch (e) {
          console.error(e);
          setAccessValues({ granted: false, error: e instanceof Error ? e.message : String(e) });
      }
  };

  const [autoLoadAttempted, setAutoLoadAttempted] = useState(false);

  useEffect(() => {
     if (datasetData && status !== "loading" && !autoLoadAttempted && !accessValues.granted && !accessValues.error) {
         if (isZarr(datasetData.media_type) && (datasetData.effective_access_level === 'public' || status === "authenticated")) {
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
        //    and take the slice for this group.
        const metadata = await getJson(`${origin}/${prefixPath}/zarr.json`);
        if (metadata) {
           setZarrMetadata(metadata);

           let resolved = sliceConsolidated(metadata, "");
           if (!resolved && metadata.members) {
               resolved = { nodes: metadata.members, items: metadata.members };
           }
           if (!resolved) {
               const rootRef = zarrRootOf(prefixPath);
               if (rootRef) {
                   const rootMeta = await getJson(`${origin}/${rootRef.root}/zarr.json`);
                   if (rootMeta) resolved = sliceConsolidated(rootMeta, rootRef.group);
               }
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

          // Reading one coordinate does not depend on reading another, so they go
          // out together rather than one round trip after the next.
          const readArray = async (name: string) => {
              const arr = await zarr.open(root.resolve(name), { kind: "array" });
              return toFloatArray((await zarr.get(arr)).data);
          };

          const dataArr = await zarr.open(root.resolve(varName), { kind: "array" });
          const view = await zarr.get(dataArr);
          const viewData = toFloatArray(view.data);

          // Coordinate Array Matching
          const dataAxisNames = allItems[varName]?.dimension_names || [];

          let xData: Float32Array | Float64Array | undefined;
          let xL: string | undefined;
          let yAxisL: string | undefined;
          let xIdx: number | undefined;
          let yIdx: number | undefined;
          let sliders: { name: string, data?: Float32Array | Float64Array, shapeSize: number, idx: number }[] = [];

          if (dataAxisNames.length === 1) {
              xL = dataAxisNames.find((d: string) => coordsList.includes(d));
              xIdx = 0;
              if (xL) {
                  xData = await readArray(xL);
              }
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

              // One scalar slider per non-X, non-Y dimension. The X coordinate and
              // every slider coordinate are independent reads, so issue them as a
              // single batch: over a remote store this is the difference between
              // one round trip and one per axis.
              const sliderDims = dataAxisNames
                  .map((name: string, i: number) => ({ name, i }))
                  .filter(({ i }: { i: number }) => i !== xIdx && i !== yIdx);

              const xName = xL;
              const [xResult, ...sliderResults] = await Promise.all([
                  xName && coordsList.includes(xName) ? readArray(xName) : Promise.resolve(undefined),
                  ...sliderDims.map(({ name }: { name: string }) =>
                      coordsList.includes(name) ? readArray(name) : Promise.resolve(undefined)
                  ),
              ]);

              xData = xResult;
              sliders = sliderDims.map(({ name, i }: { name: string; i: number }, n: number) => ({
                  name,
                  data: sliderResults[n],
                  shapeSize: view.shape[i],
                  idx: i,
              }));
          }

          setChunkData({
              data: viewData,
              shape: view.shape,
              x: xData as Float32Array | Float64Array | undefined,
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
      if (!accessValues.token || !accessValues.s3Path) return;

      const access = accessValues.token as DataAccess;
      const { path: prefixPath } = objectUrl(access.endpointUrl, accessValues.s3Path);

      // Use the metadata resolved when the dataset was opened. Re-deriving it from
      // the group's own zarr.json loses everything for a store that consolidates
      // only at its root, which leaves the variable with no dimensions and so no
      // axes and no sliders.
      const items = groupMeta.current?.items;
      if (!items) return;
      fetchVariables(access, prefixPath, newVar, coordinates, items);
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Code Snippet Modal */}
      {showCodeModal && accessValues.token && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-xl max-w-3xl w-full shadow-2xl relative overflow-hidden animate-fade-in">
              <div className="flex justify-between items-center bg-muted p-4 border-b border-border">
                  <h3 className="text-lg font-bold text-foreground flex items-center gap-2"><Activity className="w-5 h-5 text-primary"/> Connect via Python (Xarray)</h3>
                  <button onClick={() => setShowCodeModal(false)} className="text-muted-foreground hover:text-foreground text-2xl leading-none">&times;</button>
              </div>
              <div className="p-6">
                  <p className="text-sm text-foreground mb-4">
                      To prevent dark repositories and ensure you always analyze the latest version of the data, we recommend streaming directly into Python.
                      {(accessValues.token as DataAccess | null)?.anon
                        ? " This data is openly published, so it opens anonymously: no credentials, and the read goes straight to the store holding it."
                        : " Your temporary access token has been injected below."}
                  </p>
                  <div className="bg-background p-4 rounded-lg overflow-x-auto border border-border relative group">
                      {(() => {
                          const snippet = buildSnippet(datasetData?.media_type, accessValues.token as DataAccess, accessValues.s3Path!);
                          return (
                              <>
                                  <button
                                      onClick={() => navigator.clipboard.writeText(snippet)}
                                      className="absolute top-2 right-2 bg-muted hover:bg-muted text-xs text-foreground px-3 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                                  >Copy Snippet</button>
                                  <pre className="text-foreground text-sm font-mono whitespace-pre-wrap">{snippet}</pre>
                              </>
                          );
                      })()}
                  </div>
                  <div className="mt-4 bg-muted border border-border p-3 rounded flex gap-3 text-sm text-foreground">
                      <span className="font-bold shrink-0">Note:</span>
                      <p>This S3 STS token is temporary and scoped exclusively to your authenticated identity profile. Do not commit this code snippet to version control.</p>
                  </div>
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
         <p className="text-lg text-foreground max-w-4xl leading-relaxed mb-6">
            {datasetData?.description || "Scientific data array containing experimental measurements from the plasma discharge."}
         </p>
         <div className="flex flex-wrap gap-3">
             {device && <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">Device: {deviceLabel}</span>}
             {shot && <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">Shot: {shot}</span>}
             {datasetData?.publisher && <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border">Publisher: {datasetData.publisher}</span>}
             {datasetData?.annotates && (
                <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border flex items-center gap-1">
                    <Highlighter className="w-3.5 h-3.5" />
                    Annotates: {datasetData.annotates}
                </span>
             )}
         </div>
      </div>

      <div className={datasetData && !isZarr(datasetData.media_type) ? 'max-w-3xl' : 'grid grid-cols-1 lg:grid-cols-3 gap-8'}>

        {/* Left Column: Zarr Visualizer (only rendered for Zarr datasets) */}
        {(!datasetData || isZarr(datasetData.media_type)) && (
          <div className="lg:col-span-2">
            <div className="card h-[650px] flex flex-col relative overflow-hidden shadow-2xl shadow-black/50 border border-border">
                <div className="absolute inset-0 bg-background/80 z-0">
                    {/* Grid Background Pattern */}
                    <div className="h-full w-full opacity-30" style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.2) 1px, transparent 1px)', backgroundSize: '30px 30px' }}></div>
                </div>

                <div className="relative z-10 p-4 flex justify-between items-center border-b border-border bg-card/90 backdrop-blur">
                    <h3 className="font-mono text-sm text-foreground flex items-center gap-2 font-bold tracking-wider">
                        <Activity className="w-4 h-4" /> INTERACTIVE ZARR VISUALIZER
                    </h3>
                    <div className="flex gap-2">
                        {variables.length > 0 && (
                            <span className="text-xs bg-muted border border-border px-2 py-1 rounded text-foreground">{variables.length} array variables</span>
                        )}
                    </div>
                </div>

                <div className="flex-1 flex items-center justify-center relative z-10">
                    {!accessValues.granted ? (
                        <div className="text-center p-8 bg-card/50 backdrop-blur border border-border rounded-lg max-w-md">
                            <Lock className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                            <h4 className="text-lg font-bold text-foreground mb-2">Data Locked</h4>
                            <p className="text-muted-foreground text-sm mb-6">Authenticate to decrypt and visualize this Zarr store natively in your browser.</p>
                            <button
                                onClick={handleRequestAccess}
                                className="bg-primary hover:bg-accent text-foreground font-bold py-2 px-6 rounded transition-colors flex items-center justify-center gap-2 mx-auto"
                            >
                                <Unlock className="w-4 h-4" />
                                {status === "authenticated" ? "Grant Access" : "Sign In"}
                            </button>
                        </div>
                    ) : (
                        <div className="w-full h-full flex flex-col items-start justify-start p-0">
                            {/* Visualizer Toolbar */}
                            <div className="w-full bg-card/80 border-b border-border p-4 flex gap-4 items-center backdrop-blur">
                                <span className="text-sm font-medium text-muted-foreground">Variable:</span>
                                {variables.length > 0 ? (
                                    <select
                                        className="bg-background border border-border text-foreground text-sm rounded focus:ring-primary focus:border-primary block p-2 shadow-inner min-w-[200px]"
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
                                    <div className="flex flex-col items-center bg-card/50 p-6 rounded-lg backdrop-blur max-w-md text-center">
                                        <Lock className="w-8 h-8 text-destructive mb-4" />
                                        <p className="text-sm text-foreground font-medium">Could not read the data</p>
                                        <p className="text-xs text-muted-foreground mt-2 break-words">{loadError}</p>
                                        <p className="text-[11px] text-muted-foreground mt-3">
                                            The metadata above comes from FDS; the data itself is served by the store holding it, which may be unreachable or rate-limiting.
                                        </p>
                                    </div>
                                ) : loadingData || progress ? (
                                    <div className="flex flex-col items-center bg-card/50 p-6 rounded-lg backdrop-blur min-w-[18rem]">
                                        <Activity className="w-8 h-8 text-primary animate-spin mb-4" />
                                        <p className="text-sm text-foreground font-medium">
                                            {progress?.label ?? "Reading data"}
                                        </p>
                                        {progress && (
                                          <>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                streaming from <span className="font-mono">{progress.host}</span>
                                            </p>
                                            <div className="w-full h-1 bg-muted rounded overflow-hidden mt-3">
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
                                            <div key={slider.name} className="w-full max-w-3xl bg-card border border-border p-3 rounded mb-2 flex gap-4 items-center shadow-lg">
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
                                                            <p className="text-xs text-muted-foreground mt-4 bg-card px-3 py-1 rounded font-mono">
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
                                                            <p className="text-xs text-muted-foreground mt-4 bg-card px-3 py-1 rounded-full border border-border shadow flex items-center gap-2 font-mono">
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

        {/* Right Column: Metadata & Controls Sidebar */}
        <div className="space-y-6">

            <div className="card p-6 border-t-4 border-t-primary bg-muted/80 shadow-xl border-border">
                <h3 className="text-lg font-bold mb-4 flex items-center justify-between text-foreground">
                    Data Access
                    {accessValues.granted ? <Unlock className="w-5 h-5 text-foreground" /> : <Lock className="w-5 h-5 text-muted-foreground" />}
                </h3>

                {!accessValues.granted ? (
                    <div className="text-left">
                        <p className="text-muted-foreground text-sm mb-6 leading-relaxed">
                          {datasetData?.effective_access_level === 'public'
                            ? 'This dataset is publicly accessible. Click below to load credentials.'
                            : 'Dataset files are secured in MinIO S3. Authenticate with an FDS account to acquire an S3 token.'}
                        </p>
                        {accessValues.error && <p className="text-destructive mb-4 text-sm bg-destructive/10 p-2 rounded border border-destructive/40">{accessValues.error}</p>}
                        <button
                            onClick={handleRequestAccess}
                            className="bg-primary hover:bg-accent text-foreground font-bold py-3 px-4 rounded w-full transition-colors flex items-center justify-center gap-2 shadow-lg hover:shadow-primary/25"
                        >
                            <Unlock className="w-4 h-4" />
                            {datasetData?.effective_access_level === 'public'
                              ? 'Load Data'
                              : status === "authenticated" ? "Request S3 Token" : "Sign In to Access"}
                        </button>
                    </div>
                ) : (
                    <div className="animate-fade-in text-sm">
                        <div className="bg-muted border border-border text-foreground p-3 rounded mb-4 flex items-center gap-2 shadow-inner">
                            <span className="w-2 h-2 rounded-full bg-muted animate-pulse"></span> Identity Verified
                        </div>
                        <div className="space-y-2 text-xs">
                           <p className="text-muted-foreground font-medium uppercase tracking-wider">Mounted URI</p>
                           <p className="break-all text-foreground font-mono bg-card border border-border p-2 rounded">{accessValues.s3Path}</p>
                           <a href="#" onClick={(e) => { e.preventDefault(); setShowCodeModal(true); }} className="text-primary hover:text-foreground inline-flex items-center gap-1 mt-2">
                               <Download className="w-3 h-3" /> Download Dataset
                           </a>
                        </div>
                    </div>
                )}
            </div>

            <div className="card p-6 bg-card/60 shadow-xl border-border">
                <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground">Dataset Properties</h3>
                <div className="space-y-3 text-sm">
                    <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                        <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Created At</span>
                        <span className="text-foreground">{datasetData?.created_at ? new Date(datasetData.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric'}) : 'Unknown'}</span>
                    </div>
                    <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                        <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Media Type</span>
                        <span className="text-foreground">{datasetData?.media_type || 'Unknown'}</span>
                    </div>
                    {datasetData?.license && (
                        <div className="flex flex-col justify-start py-1 border-b border-border pb-2">
                            <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">License</span>
                            <span className="text-foreground">{datasetData.license}</span>
                        </div>
                    )}
                     <div className="flex flex-col justify-start py-1">
                        <span className="text-muted-foreground uppercase text-xs font-bold tracking-wider mb-1">Access Level</span>
                        <span className="text-foreground capitalize">{datasetData?.effective_access_level || datasetData?.access_level || 'Unknown'}</span>
                    </div>
                </div>
            </div>

            {/* Features annotated on this dataset's own axes */}
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
                                <span className="font-mono text-foreground">{activityData.source_version}</span>
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
                                <pre className="text-xs text-foreground font-mono bg-background border border-border p-2 rounded overflow-x-auto">
                                    {JSON.stringify(activityData.parameters, null, 2)}
                                </pre>
                            </div>
                        )}
                        <Link
                            href="/sources"
                            className="text-xs text-primary hover:text-foreground inline-flex items-center gap-1 mt-2 transition-colors"
                        >
                            View Sources <ChevronRight className="w-3 h-3" />
                        </Link>
                    </div>
                ) : datasetData?.activity_id ? (
                    <p className="text-muted-foreground text-sm">Loading provenance...</p>
                ) : (
                    <div className="text-center py-4 bg-card/30 rounded-lg border border-dashed border-border">
                        <p className="text-xs text-muted-foreground">No provenance recorded for this dataset.</p>
                    </div>
                )}
            </div>

        </div>

      </div>

      {datasetData?.id && datasetData?.activity_id ? (
        <div className="card p-6 mt-8 bg-card/60 shadow-xl border-border">
          <h3 className="text-lg font-bold mb-4 border-b border-border pb-2 text-foreground flex items-center gap-2">
            <Activity className="w-5 h-5 text-muted-foreground" /> Provenance Graph
          </h3>
          <ProvenanceGraph datasetId={datasetData.id} />
        </div>
      ) : null}
    </div>
  );
}
