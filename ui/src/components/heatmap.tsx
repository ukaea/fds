'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

type Values = Float32Array | Float64Array;

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

export interface HeatmapAxis {
    label: string;
    units?: string;
    // The coordinate at each grid index. Without it the axis counts indices.
    coords?: Values;
}

interface HeatmapProps {
    // Row-major: data[row * width + column], with rows along y.
    data: Values;
    width: number;
    height: number;
    x: HeatmapAxis;
    y: HeatmapAxis;
    value: { label: string; units?: string };
    title: string;
}

interface AxisScale {
    lo: number;
    hi: number;
    // Position of a (possibly fractional) grid index, from 0 at lo to 1 at hi.
    frac: (index: number) => number;
    label: string;
}

// Cells are centred on their coordinates, so the axis runs half a cell past the
// first and last values. Spacing is taken as even, as it is in the image.
function axisScale(axis: HeatmapAxis, n: number): AxisScale & { physical: boolean; units?: string } {
    const c = axis.coords;
    const physical = Boolean(
        c && c.length === n && n > 1
        && Number.isFinite(c[0]) && Number.isFinite(c[n - 1]) && c[0] !== c[n - 1]
    );
    const first = physical ? c![0] : 0;
    const step = physical ? (c![n - 1] - first) / (n - 1) : 1;
    const a = first - step / 2;
    const b = first + (n - 1) * step + step / 2;
    const lo = Math.min(a, b), hi = Math.max(a, b);
    const units = physical ? axis.units : undefined;
    return {
        lo,
        hi,
        frac: (index) => (first + index * step - lo) / (hi - lo),
        label: units ? `${axis.label} (${units})` : physical ? axis.label : `${axis.label} (index)`,
        physical,
        units,
    };
}

function niceTicks(lo: number, hi: number, count: number): { values: number[]; step: number } {
    const raw = (hi - lo) / Math.max(1, count);
    const mag = 10 ** Math.floor(Math.log10(raw));
    const norm = raw / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const values: number[] = [];
    for (let k = Math.ceil(lo / step); k * step <= hi + step * 1e-9; k++) values.push(k * step);
    return { values, step };
}

function formatTick(v: number, step: number): string {
    if (v === 0) return '0';
    if (Math.abs(v) >= 1e5 || step < 1e-3) return v.toExponential(1);
    return v.toFixed(Math.max(0, -Math.floor(Math.log10(step) + 1e-9)));
}

// Contour lines at one level by marching squares. Each segment is four numbers,
// [column, row, column, row], in fractional grid indices.
function contourSegments(data: Values, width: number, height: number, level: number): number[] {
    const out: number[] = [];
    for (let j = 0; j < height - 1; j++) {
        for (let i = 0; i < width - 1; i++) {
            const a = data[j * width + i], b = data[j * width + i + 1];
            const c = data[(j + 1) * width + i + 1], d = data[(j + 1) * width + i];
            if (!(Number.isFinite(a) && Number.isFinite(b) && Number.isFinite(c) && Number.isFinite(d))) continue;
            const above = [a > level, b > level, c > level, d > level];
            if (above.every(Boolean) || !above.some(Boolean)) continue;
            // Where the level crosses edges a-b, b-c, c-d and d-a, in that order.
            const cross = [
                above[0] !== above[1] ? [i + (level - a) / (b - a), j] : null,
                above[1] !== above[2] ? [i + 1, j + (level - b) / (c - b)] : null,
                above[2] !== above[3] ? [i + 1 - (level - c) / (d - c), j + 1] : null,
                above[3] !== above[0] ? [i, j + 1 - (level - d) / (a - d)] : null,
            ];
            const join = (p: number[] | null, q: number[] | null) => { if (p && q) out.push(p[0], p[1], q[0], q[1]); };
            const hits = cross.filter((p): p is number[] => p !== null);
            if (hits.length === 2) {
                join(hits[0], hits[1]);
            } else if ((a + b + c + d) / 4 > level !== above[0]) {
                // A saddle: the centre value decides which corners the lines cut off.
                join(cross[3], cross[0]);
                join(cross[1], cross[2]);
            } else {
                join(cross[0], cross[1]);
                join(cross[2], cross[3]);
            }
        }
    }
    return out;
}

const MARGIN = { left: 64, right: 104, top: 8, bottom: 40 };

export function HeatmapCanvas({ data, width, height, x, y, value, title }: HeatmapProps) {
    const boxRef = useRef<HTMLDivElement>(null);
    const [size, setSize] = useState({ w: 0, h: 0 });
    const [showContours, setShowContours] = useState(false);

    useEffect(() => {
        const box = boxRef.current;
        if (!box) return;
        const observer = new ResizeObserver(([entry]) =>
            setSize({ w: entry.contentRect.width, h: entry.contentRect.height })
        );
        observer.observe(box);
        return () => observer.disconnect();
    }, []);

    let min = Infinity, max = -Infinity;
    for (let i = 0; i < data.length; i++) {
        if (Number.isFinite(data[i])) {
            if (data[i] < min) min = data[i];
            if (data[i] > max) max = data[i];
        }
    }
    // A slice outside the reconstruction window is entirely NaN. Normalising it
    // yields NaN everywhere, which paints a uniform square that looks like data.
    // Say the slice is empty instead.
    const hasData = Number.isFinite(min);
    if (!hasData || min === max) { min = (hasData ? min : 0) - 1; max = (hasData ? max : 0) + 1; }

    const xs = axisScale(x, width);
    const ys = axisScale(y, height);

    // Missing values stay transparent rather than taking the colour of the minimum.
    const image = useMemo(() => {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) return '';
        const img = ctx.createImageData(width, height);
        for (let j = 0; j < height; j++) {
            const row = Math.round((1 - ys.frac(j)) * height - 0.5);
            for (let i = 0; i < width; i++) {
                const v = data[j * width + i];
                if (!Number.isFinite(v)) continue;
                const p = (row * width + Math.round(xs.frac(i) * width - 0.5)) * 4;
                const rgb = getViridisColor((v - min) / (max - min));
                img.data[p] = rgb[0];
                img.data[p + 1] = rgb[1];
                img.data[p + 2] = rgb[2];
                img.data[p + 3] = 255;
            }
        }
        ctx.putImageData(img, 0, 0);
        return canvas.toDataURL();
    // xs and ys are rebuilt each render but follow from the coordinates and sizes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data, width, height, min, max, x.coords, y.coords]);

    const contours = useMemo(() => {
        if (!showContours || !hasData) return [];
        return niceTicks(min, max, 14).values
            .filter((level) => level > min && level < max)
            .map((level) => contourSegments(data, width, height, level));
    }, [showContours, hasData, data, width, height, min, max]);

    // Axes in the same units are drawn to the same scale, so a poloidal
    // cross-section keeps its shape. Otherwise the plot fills the space.
    const availW = Math.max(0, size.w - MARGIN.left - MARGIN.right);
    const availH = Math.max(0, size.h - MARGIN.top - MARGIN.bottom);
    let plotW = availW, plotH = availH;
    if (xs.physical && ys.physical && xs.units && xs.units === ys.units) {
        const scale = Math.min(availW / (xs.hi - xs.lo), availH / (ys.hi - ys.lo));
        plotW = (xs.hi - xs.lo) * scale;
        plotH = (ys.hi - ys.lo) * scale;
    }
    const left = MARGIN.left + (availW - plotW) / 2;
    const top = MARGIN.top + (availH - plotH) / 2;
    const px = (v: number) => left + (v - xs.lo) / (xs.hi - xs.lo) * plotW;
    const py = (v: number) => top + (1 - (v - ys.lo) / (ys.hi - ys.lo)) * plotH;
    const ix = (i: number) => left + xs.frac(i) * plotW;
    const iy = (j: number) => top + (1 - ys.frac(j)) * plotH;

    const xTicks = niceTicks(xs.lo, xs.hi, Math.max(3, Math.floor(plotW / 80)));
    const yTicks = niceTicks(ys.lo, ys.hi, Math.max(3, Math.floor(plotH / 50)));
    const vTicks = niceTicks(min, max, Math.max(3, Math.floor(plotH / 50)));
    const barX = left + plotW + 16;
    const valueLabel = value.units ? `${value.label} (${value.units})` : value.label;

    return (
        <div className="w-full flex-1 min-h-0 flex flex-col items-center p-2">
            <div ref={boxRef} className="relative w-full flex-1 min-h-[280px]">
                {!hasData ? (
                    <div className="absolute inset-0 m-auto max-w-[300px] h-[200px] border border-border border-dashed rounded flex items-center justify-center p-4">
                        <p className="text-xs text-muted-foreground text-center">
                            No data at this index.<br />Move the slider into the reconstruction window.
                        </p>
                    </div>
                ) : plotW > 0 && plotH > 0 && (
                    <svg width={size.w} height={size.h} className="absolute inset-0 text-muted-foreground" fontSize={10} role="img" aria-label={title}>
                        <defs>
                            <linearGradient id="heatmap-viridis" x1="0" y1="1" x2="0" y2="0">
                                {VIRIDIS_STOPS.map((c, k) => (
                                    <stop key={k} offset={k / (VIRIDIS_STOPS.length - 1)} stopColor={`rgb(${c.join(',')})`} />
                                ))}
                            </linearGradient>
                        </defs>
                        <image
                            href={image}
                            x={left}
                            y={top}
                            width={plotW}
                            height={plotH}
                            preserveAspectRatio="none"
                            style={{ imageRendering: 'pixelated' }}
                        />
                        {contours.map((segments, k) => (
                            <path
                                key={k}
                                d={Array.from({ length: segments.length / 4 }, (_, s) => {
                                    const [i1, j1, i2, j2] = segments.slice(s * 4, s * 4 + 4);
                                    return `M${ix(i1).toFixed(1)},${iy(j1).toFixed(1)}L${ix(i2).toFixed(1)},${iy(j2).toFixed(1)}`;
                                }).join('')}
                                fill="none"
                                stroke="rgba(255,255,255,0.75)"
                                strokeWidth={1}
                            />
                        ))}
                        <rect x={left} y={top} width={plotW} height={plotH} fill="none" stroke="currentColor" strokeOpacity={0.5} />

                        {xTicks.values.map((v) => (
                            <g key={`x${v}`} fill="currentColor" stroke="currentColor">
                                <line x1={px(v)} x2={px(v)} y1={top + plotH} y2={top + plotH + 4} />
                                <text x={px(v)} y={top + plotH + 15} textAnchor="middle" stroke="none">{formatTick(v, xTicks.step)}</text>
                            </g>
                        ))}
                        <text x={left + plotW / 2} y={top + plotH + 32} textAnchor="middle" fill="currentColor">{xs.label}</text>

                        {yTicks.values.map((v) => (
                            <g key={`y${v}`} fill="currentColor" stroke="currentColor">
                                <line x1={left - 4} x2={left} y1={py(v)} y2={py(v)} />
                                <text x={left - 7} y={py(v) + 3} textAnchor="end" stroke="none">{formatTick(v, yTicks.step)}</text>
                            </g>
                        ))}
                        <text
                            transform={`translate(${left - 50},${top + plotH / 2}) rotate(-90)`}
                            textAnchor="middle"
                            fill="currentColor"
                        >
                            {ys.label}
                        </text>

                        <rect x={barX} y={top} width={12} height={plotH} fill="url(#heatmap-viridis)" />
                        {vTicks.values.filter((v) => v >= min && v <= max).map((v) => {
                            const vy = top + (1 - (v - min) / (max - min)) * plotH;
                            return (
                                <g key={`v${v}`} fill="currentColor" stroke="currentColor">
                                    <line x1={barX + 12} x2={barX + 16} y1={vy} y2={vy} />
                                    <text x={barX + 19} y={vy + 3} stroke="none">{formatTick(v, vTicks.step)}</text>
                                </g>
                            );
                        })}
                        <text
                            transform={`translate(${barX + 76},${top + plotH / 2}) rotate(90)`}
                            textAnchor="middle"
                            fill="currentColor"
                        >
                            {valueLabel}
                        </text>
                    </svg>
                )}
            </div>
            <div className="mt-2 flex items-center gap-2">
                <p className="text-xs text-muted-foreground bg-card px-3 py-1 rounded inline-flex font-mono">
                    Heatmap: {title}
                </p>
                <button
                    type="button"
                    aria-pressed={showContours}
                    onClick={() => setShowContours((on) => !on)}
                    className={`text-xs font-mono px-3 py-1 rounded border transition-colors ${showContours ? 'border-primary text-foreground bg-primary/15' : 'border-border text-muted-foreground bg-card hover:text-foreground'}`}
                >
                    Contours
                </button>
            </div>
        </div>
    );
}
