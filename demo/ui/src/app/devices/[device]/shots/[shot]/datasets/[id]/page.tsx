'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Database, Lock, Unlock, Download, Activity, ArrowLeft, ChevronRight, MapPin, SlidersHorizontal, Highlighter } from 'lucide-react';
import { useSession, signIn } from "next-auth/react";
import useSWR from 'swr';
import { fetcher, API_BASE } from '@/lib/api';
import { Activity as ActivityType, Dataset } from '@/lib/types';
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

function HeatmapCanvas({ data, width, height, title }: any) {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let min = Infinity, max = -Infinity;
        for (let i = 0; i < data.length; i++) {
            if (!Number.isNaN(data[i])) {
                if (data[i] < min) min = data[i];
                if (data[i] > max) max = data[i];
            }
        }
        if (min === max) { min -= 1; max += 1; }

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
             <canvas
                ref={canvasRef}
                width={width}
                height={height}
                className="w-full max-w-[300px] aspect-square object-contain pixelated border border-border bg-black/50"
                style={{ imageRendering: 'pixelated' }}
             />
             <p className="text-xs text-muted-foreground mt-4 bg-card px-3 py-1 rounded inline-flex font-mono">
                 Heatmap: {title}
             </p>
        </div>
    );
}

function isZarr(mediaType?: string | null): boolean {
  return Boolean(mediaType?.toLowerCase().includes('zarr'));
}

function formatMediaType(mediaType?: string | null): string {
  if (!mediaType) return 'Unknown';
  if (mediaType.includes('zarr')) return 'Zarr';
  if (mediaType.includes('netcdf') || mediaType.includes('netCDF')) return 'NetCDF';
  if (mediaType.includes('hdf')) return 'HDF5';
  return mediaType.split('/').pop() || mediaType;
}

function buildSnippet(
  mediaType: string | null | undefined,
  creds: { access_key_id: string; secret_access_key: string; session_token: string },
  s3Path: string,
): string {
  const storageOptions = `storage_options = {
    "key": "${creds.access_key_id}",
    "secret": "${creds.secret_access_key}",
    "token": "${creds.session_token}",
    "client_kwargs": {
        "endpoint_url": "http://localhost:9000"
    }
}`;

  if (isZarr(mediaType)) {
    return `import xarray as xr

${storageOptions}

ds = xr.open_zarr("${s3Path}", storage_options=storage_options)
print(ds)`;
  }

  // NetCDF / HDF5: fs.cat + BytesIO avoids the HeadObject call that
  // xr.open_dataset(s3_url, ...) makes — our STS session policy grants
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

export default function DatasetPage() {
  const params = useParams();
  const { device, shot, id } = params;
  const deviceLabel = useDeviceLabel(device as string);

  const { data: session, status } = useSession();
  const [accessValues, setAccessValues] = useState<{granted: boolean, token?: any, s3Path?: string, error?: string}>({ granted: false });
  const [zarrMetadata, setZarrMetadata] = useState<any>(null);
  const [showCodeModal, setShowCodeModal] = useState(false);
  const [variables, setVariables] = useState<string[]>([]);
  const [coordinates, setCoordinates] = useState<string[]>([]);
  const [selectedVar, setSelectedVar] = useState<string | null>(null);
  const [chunkData, setChunkData] = useState<{ data: Float32Array | Float64Array, shape: number[], x?: Float32Array | Float64Array, yL?: string, xL?: string, xIdx?: number, yIdx?: number, yAxisL?: string, sliders?: { name: string, data?: Float32Array | Float64Array, shapeSize: number, idx: number }[] } | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [sliderIndices, setSliderIndices] = useState<number[]>([]);

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

  const handleRequestAccess = async () => {
      if (datasetData?.effective_access_level !== "public" && status !== "authenticated") {
          signIn("keycloak");
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
          const s3Path = datasetData?.url;

          // resource_map maps URL → credential directly
          const validCreds = manifest.resource_map[s3Path || ""] ?? null;

          if (validCreds && s3Path) {
             setAccessValues({ granted: true, token: validCreds, s3Path });
             loadZarrData(validCreds, s3Path);
          } else {
             setAccessValues({ granted: false, error: "No valid token retrieved for this dataset." });
          }

      } catch (e: any) {
          console.error(e);
          setAccessValues({ granted: false, error: e.message });
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

  const loadZarrData = async (creds: any, s3Path: string) => {
      // s3Path is like "s3://fds-data/shots/30421/equilibrium"
      const url = new URL(s3Path.replace("s3://", "http://localhost:9000/"));
      const bucket = url.pathname.split('/')[1];
      const prefixPath = url.pathname.split('/').slice(2).join('/');

      const zarrJsonUrl = `${url.origin}/${bucket}/${prefixPath}/zarr.json`;

      // Extract credential specifically for this bucket if it's nested
      const activeCreds = creds[bucket] || creds;

      // aws4fetch client initialization is missing here, adding it
      const { AwsClient } = await import('aws4fetch');
      const awsClient = new AwsClient({
        accessKeyId: activeCreds.access_key_id,
        secretAccessKey: activeCreds.secret_access_key,
        sessionToken: activeCreds.session_token,
        region: activeCreds.region || 'us-east-1',
        service: 's3'
      });

      try {
        // 1. Fetch group metadata
        const response = await awsClient.fetch(zarrJsonUrl);
        if (response.ok) {
           const metadata = await response.json();
           setZarrMetadata(metadata);

           // 2. Extract arrays from Zarr v3 members object or consolidated metadata
           let items: Record<string, any> = {};
           if (metadata.consolidated_metadata?.metadata) {
               items = metadata.consolidated_metadata.metadata;
           } else if (metadata.members) {
               items = metadata.members;
           }

           const arrayNames = Object.keys(items).filter(key =>
               items[key]?.node_type === 'array' || items[key]?.attributes?.name
           );

           const allDimNames = new Set<string>();
           arrayNames.forEach(k => {
               const dims = items[k].dimension_names || [];
               dims.forEach((d: string) => allDimNames.add(d));
           });

           const coords = arrayNames.filter(k =>
               allDimNames.has(k) || (items[k].dimension_names?.length === 1 && items[k].dimension_names[0] === k)
           );
           setCoordinates(coords);

           const dataVars = arrayNames.filter(k => !coords.includes(k) && !k.includes("/"));

           console.log("CACHE BUST: Extracted Data Vars:", dataVars);
           setVariables(dataVars);
           if (dataVars.length > 0) {
               setSelectedVar(dataVars[0]);
               fetchVariables(activeCreds, bucket, prefixPath, dataVars[0], coords, items);
           }
        } else {
           console.error("Failed to load Zarr metadata:", response.statusText);
        }
      } catch (err) {
        console.error("Zarr fetch error:", err);
      }
  };

  const fetchVariables = async (activeCreds: any, bucket: string, prefixPath: string, varName: string, coordsList: string[], allItems: any) => {
      setLoadingData(true);
      try {
          const { AwsClient } = await import('aws4fetch');
          const zarr = await import('zarrita');

          const awsClient = new AwsClient({
            accessKeyId: activeCreds.access_key_id,
            secretAccessKey: activeCreds.secret_access_key,
            sessionToken: activeCreds.session_token,
            region: activeCreds.region || 'us-east-1',
            service: 's3'
          });

          const prefix = prefixPath ? `${prefixPath}/` : '';
          const storeUrl = `http://localhost:9000/${bucket}/${prefix.replace(/\/$/, '')}`;

          const customStore = {
              async get(key: string) {
                  const cleanKey = key.startsWith('/') ? key.slice(1) : key;
                  const res = await awsClient.fetch(`${storeUrl}/${cleanKey}`);
                  if (res.status === 404 || res.status === 403) return undefined;
                  if (!res.ok) throw new Error(`Fetch failed: ${res.statusText}`);
                  return new Uint8Array(await res.arrayBuffer());
              }
          };

          const root = zarr.root(customStore);

          const dataArr = await zarr.open(root.resolve(varName), { kind: "array" });
          const view = await zarr.get(dataArr);

          // Coordinate Array Matching
          const dataAxisNames = allItems[varName]?.dimension_names || [];

          let xData;
          let xL;
          let yAxisL;
          let xIdx;
          let yIdx;
          let sliders: { name: string, data?: Float32Array | Float64Array, shapeSize: number, idx: number }[] = [];

          if (dataAxisNames.length === 1) {
              xL = dataAxisNames.find((d: string) => coordsList.includes(d));
              xIdx = 0;
              if (xL) {
                  const xArr = await zarr.open(root.resolve(xL), { kind: "array" });
                  xData = (await zarr.get(xArr)).data;
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
              if (coordsList.includes(xL)) {
                  const xArr = await zarr.open(root.resolve(xL), { kind: "array" });
                  xData = (await zarr.get(xArr)).data;
              }

              // Build a scalar slider for every non-X, non-Y dimension
              for (let i = 0; i < dataAxisNames.length; i++) {
                  if (i !== xIdx && i !== yIdx) {
                      const dimName = dataAxisNames[i];
                      let dimData;
                      if (coordsList.includes(dimName)) {
                          const sArr = await zarr.open(root.resolve(dimName), { kind: "array" });
                          dimData = (await zarr.get(sArr)).data as Float32Array | Float64Array;
                      }
                      sliders.push({ name: dimName, data: dimData, shapeSize: view.shape[i], idx: i });
                  }
              }
          }

          setChunkData({
              data: view.data as Float32Array | Float64Array,
              shape: view.shape,
              x: xData as Float32Array | Float64Array | undefined,
              yL: varName,
              xL: xL,
              yAxisL,
              xIdx,
              yIdx,
              sliders
          });
          setSliderIndices(sliders.map(() => 0));
      } catch (err) {
          console.error("Zarrita chunk fetch error:", err);
      } finally {
         setLoadingData(false);
      }
  };

  const onSelectVariable = async (newVar: string) => {
      setSelectedVar(newVar);
      if (!accessValues.token || !accessValues.s3Path || !zarrMetadata) return;

      const url = new URL(accessValues.s3Path.replace("s3://", "http://localhost:9000/"));
      const bucket = url.pathname.split('/')[1];
      const prefixPath = url.pathname.split('/').slice(2).join('/');
      const activeCreds = accessValues.token[bucket] || accessValues.token;

      let items: any = zarrMetadata.consolidated_metadata?.metadata || zarrMetadata.members || {};
      fetchVariables(activeCreds, bucket, prefixPath, newVar, coordinates, items);
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
                      To prevent dark repositories and ensure you always analyze the latest version of the data, we recommend streaming directly into Python. Your temporary access token has been injected below.
                  </p>
                  <div className="bg-background p-4 rounded-lg overflow-x-auto border border-border relative group">
                      {(() => {
                          const activeCreds = (() => {
                              const url = new URL(accessValues.s3Path!.replace("s3://", "http://localhost:9000/"));
                              const bucket = url.pathname.split('/')[1];
                              return accessValues.token[bucket] || accessValues.token;
                          })();
                          const snippet = buildSnippet(datasetData?.media_type, activeCreds, accessValues.s3Path!);
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
            <Link href={`/devices/${device}`} className="hover:text-primary transition-colors flex items-center">{deviceLabel}</Link>
            <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
            <Link href={`/devices/${device}/shots/${shot}`} className="hover:text-primary transition-colors flex items-center">Shot #{shot}</Link>
            <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
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
             <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">Device: {deviceLabel}</span>
             <span className="bg-muted text-foreground px-3 py-1 rounded-full text-sm border border-border font-mono">Shot: {shot}</span>
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
                                        onChange={(e: any) => {
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
                                {loadingData ? (
                                    <div className="flex flex-col items-center bg-card/50 p-6 rounded-lg backdrop-blur">
                                        <Activity className="w-8 h-8 text-primary animate-spin mb-4" />
                                        <p className="text-sm text-foreground">Fetching chunks via WebAssembly...</p>
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
                                                    onChange={(e: any) => {
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
    </div>
  );
}
