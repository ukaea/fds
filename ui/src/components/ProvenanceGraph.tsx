'use client';

import { useEffect, useRef, useState } from 'react';
import useSWR from 'swr';
import { Graphviz } from '@hpcc-js/wasm-graphviz';

import {
  buildCollectionLineage,
  buildLineage,
  type ProvAttr,
  type ProvEdgeKind,
  type ProvGraph,
  type ProvNodeKind,
} from '@/lib/provenance';
import type { Collection } from '@/lib/types';

// The three PROV-O node classes → the conventional graphviz shape + colour.
// An instrument is an Entity in PROV, so it takes the entity shape/colour.
type ShapeKind = 'entity' | 'activity' | 'agent';
const SHAPE_OF: Record<ProvNodeKind, ShapeKind> = {
  dataset: 'entity',
  instrument: 'entity',
  collection: 'entity',
  activity: 'activity',
  agent: 'agent',
};
const NODE_DOT: Record<ShapeKind, string> = {
  entity: 'shape=ellipse, style=filled, fillcolor="#fffc87", color="#d4c04a"',
  activity: 'shape=box, style="filled,rounded", fillcolor="#9fb1fc", color="#6b82e6"',
  agent: 'shape=house, style=filled, fillcolor="#fdb266", color="#e08a34"',
};
const EDGE_LABEL: Record<ProvEdgeKind, string> = {
  wasGeneratedBy: 'wasGeneratedBy',
  used: 'used',
  wasAssociatedWith: 'wasAssociatedWith',
  actedOnBehalfOf: 'actedOnBehalfOf',
  hadMember: 'hadMember',
};

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// Centred two-line node label (name over an optional smaller sub-line). A table
// keeps both lines horizontally centred inside the shape; no bold, to match the
// site's regular weight.
const nodeLabel = (name: string, sub?: string) => {
  const subRow = sub
    ? `<TR><TD ALIGN="CENTER"><FONT POINT-SIZE="8" COLOR="#4a4a4a">${esc(sub)}</FONT></TD></TR>`
    : '';
  return (
    '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">' +
    `<TR><TD ALIGN="CENTER"><FONT POINT-SIZE="11">${esc(name)}</FONT></TD></TR>` +
    subRow +
    '</TABLE>>'
  );
};

// Edge label on a white chip that hugs the text, so the edge line behind the
// text is masked without the chip's margin clipping neighbouring edges.
const edgeLabel = (text: string, color: string) =>
  '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0" BGCOLOR="white">' +
  `<TR><TD><FONT POINT-SIZE="9" COLOR="${color}">${esc(text)}</FONT></TD></TR></TABLE>>`;

// Attribute note: label column, a spacer, then the value column.
const noteLabel = (attrs: ProvAttr[]) => {
  const rows = attrs
    .map(
      (a) =>
        '<TR>' +
        `<TD ALIGN="LEFT"><FONT COLOR="#888888">${esc(a.label)}</FONT></TD>` +
        '<TD WIDTH="16"></TD>' +
        `<TD ALIGN="LEFT">${esc(a.value)}</TD>` +
        '</TR>',
    )
    .join('');
  return `<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="1">${rows}</TABLE>>`;
};

const NOTE_DOT = 'shape=note, style=filled, fillcolor="#ffffff", color="#cfcfcf", fontsize=9';
const CONNECTOR_DOT = 'style=dashed, arrowhead=none, color="#bcbcbc"';
const EDGE_COLOR = '#555555';
const edgeRoleOf = (kind: ProvEdgeKind, role?: string) =>
  kind === 'used' || kind === 'wasAssociatedWith' ? role : undefined;

function toDot(graph: ProvGraph, showAll: boolean): string {
  const L: string[] = ['digraph prov {'];
  // ranksep is modest because each edge carries an inline label node, which
  // adds an intermediate rank of its own.
  L.push('  rankdir=BT; bgcolor="transparent"; nodesep=0.4; ranksep=0.3;');
  L.push('  node [fontname="Helvetica,Arial,sans-serif", fontsize=11, penwidth=1.4];');
  L.push('  edge [fontname="Helvetica,Arial,sans-serif", color="#8a8a8a", arrowsize=0.7];');

  for (const n of graph.nodes) {
    L.push(`  "${n.id}" [${NODE_DOT[SHAPE_OF[n.kind]]}, label=${nodeLabel(n.label, n.sub)}];`);
  }

  for (const e of graph.edges) {
    // Carry the relation label on an inline node so it sits ON the edge (line
    // running through it), not offset to one side where it reads as belonging
    // to a neighbouring node. In Show all, the role note hangs off this node.
    const el = `el:${e.id}`;
    // height=0.02 collapses the node to fit the text; without it the default
    // 0.5" minimum height leaves a big gap between the label and the edge line.
    L.push(`  "${el}" [shape=plaintext, margin=0.01, height=0.02, label=${edgeLabel(EDGE_LABEL[e.kind], EDGE_COLOR)}];`);
    L.push(`  "${e.source}" -> "${el}" [arrowhead=none];`);
    L.push(`  "${el}" -> "${e.target}";`);
    const role = edgeRoleOf(e.kind, e.label);
    if (showAll && role) {
      L.push(`  "enote:${e.id}" [${NOTE_DOT}, label=${noteLabel([{ label: 'prov:hadRole', value: role }])}];`);
      L.push(`  "${el}" -> "enote:${e.id}" [${CONNECTOR_DOT}];`);
    }
  }

  if (showAll) {
    for (const n of graph.nodes) {
      if (n.attrs?.length) {
        L.push(`  "note:${n.id}" [${NOTE_DOT}, label=${noteLabel(n.attrs)}];`);
        L.push(`  "${n.id}" -> "note:${n.id}" [${CONNECTOR_DOT}];`);
      }
    }
  }

  L.push('}');
  return L.join('\n');
}

let gvPromise: Promise<Graphviz> | null = null;
const loadGraphviz = () => (gvPromise ??= Graphviz.load());

function LegendItem({ fill, border, shape, label }: { fill: string; border: string; shape: 'ellipse' | 'rect' | 'house'; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width={22} height={16} aria-hidden>
        {shape === 'ellipse' ? (
          <ellipse cx={11} cy={8} rx={9} ry={6} fill={fill} stroke={border} strokeWidth={1.3} />
        ) : shape === 'rect' ? (
          <rect x={2} y={2} width={18} height={12} rx={3} fill={fill} stroke={border} strokeWidth={1.3} />
        ) : (
          <polygon points="11,1 20,6 20,15 2,15 2,6" fill={fill} stroke={border} strokeWidth={1.3} />
        )}
      </svg>
      {label}
    </span>
  );
}

function Legend() {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
      <LegendItem fill="#fffc87" border="#d4c04a" shape="ellipse" label="Entity" />
      <LegendItem fill="#9fb1fc" border="#6b82e6" shape="rect" label="Activity" />
      <LegendItem fill="#fdb266" border="#e08a34" shape="house" label="Agent" />
      <span className="italic">hover a node for details, or toggle Show all</span>
    </div>
  );
}

type Tip = { attrs: ProvAttr[]; x: number; y: number };

type ProvenanceGraphProps =
  | { datasetId: number; collection?: undefined }
  | { collection: Collection; datasetId?: undefined };

export default function ProvenanceGraph({ datasetId, collection }: ProvenanceGraphProps) {
  const { data, error, isLoading } = useSWR<ProvGraph>(
    datasetId != null
      ? ['lineage-ds', datasetId]
      : collection?.id != null
        ? ['lineage-col', collection.id]
        : null,
    () =>
      datasetId != null
        ? buildLineage(datasetId)
        : buildCollectionLineage(collection as Collection),
  );

  const [showAll, setShowAll] = useState(false);
  const [renderError, setRenderError] = useState(false);
  const holderRef = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  useEffect(() => {
    if (!data || !holderRef.current) return;
    const holder = holderRef.current;
    let cancelled = false;
    const cleanups: Array<() => void> = [];
    let dragging = false;
    let px = 0;
    let py = 0;

    (async () => {
      try {
        const gv = await loadGraphviz();
        if (cancelled) return;
        holder.innerHTML = gv.dot(toDot(data, showAll));
        const svg = holder.querySelector('svg');
        if (!svg) return;
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        svg.style.cursor = 'grab';

        // Pan/zoom by mutating the viewBox; no external dependency.
        const vb = svg.getAttribute('viewBox');
        if (vb) {
          let [x, y, w, h] = vb.split(/\s+/).map(Number);
          const baseW = w;
          const apply = () => svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
          const onWheel = (e: WheelEvent) => {
            e.preventDefault();
            const r = svg.getBoundingClientRect();
            const mx = x + ((e.clientX - r.left) / r.width) * w;
            const my = y + ((e.clientY - r.top) / r.height) * h;
            const f = e.deltaY < 0 ? 0.9 : 1.1;
            if (w * f < baseW * 0.1 || w * f > baseW * 2) return;
            x = mx - (mx - x) * f;
            y = my - (my - y) * f;
            w *= f;
            h *= f;
            apply();
          };
          const onDown = (e: MouseEvent) => {
            dragging = true;
            px = e.clientX;
            py = e.clientY;
            svg.style.cursor = 'grabbing';
            setTip(null);
          };
          const onMove = (e: MouseEvent) => {
            if (!dragging) return;
            const r = svg.getBoundingClientRect();
            x -= ((e.clientX - px) / r.width) * w;
            y -= ((e.clientY - py) / r.height) * h;
            px = e.clientX;
            py = e.clientY;
            apply();
          };
          const onUp = () => {
            dragging = false;
            svg.style.cursor = 'grab';
          };
          svg.addEventListener('wheel', onWheel, { passive: false });
          svg.addEventListener('mousedown', onDown);
          window.addEventListener('mousemove', onMove);
          window.addEventListener('mouseup', onUp);
          cleanups.push(() => {
            svg.removeEventListener('wheel', onWheel);
            svg.removeEventListener('mousedown', onDown);
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
          });
        }

        // Hover tooltips (compact mode only; Show all already draws the notes).
        if (!showAll) {
          const byId = new Map(data.nodes.map((n) => [n.id, n]));
          holder.querySelectorAll('g.node').forEach((g) => {
            const id = g.querySelector('title')?.textContent ?? '';
            const node = byId.get(id);
            if (!node?.attrs?.length) return;
            g.addEventListener('mousemove', (ev) => {
              if (dragging) return;
              const r = holder.getBoundingClientRect();
              const me = ev as MouseEvent;
              setTip({ attrs: node.attrs!, x: me.clientX - r.left, y: me.clientY - r.top });
            });
            g.addEventListener('mouseleave', () => setTip(null));
          });
        }
      } catch {
        if (!cancelled) setRenderError(true);
      }
    })();

    return () => {
      cancelled = true;
      cleanups.forEach((c) => c());
    };
  }, [data, showAll]);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Building provenance graph…</p>;
  }
  if (error || renderError) {
    return <p className="text-sm text-muted-foreground">Could not render the provenance graph.</p>;
  }
  if (!data || data.nodes.length === 0) {
    return <p className="text-sm text-muted-foreground">No provenance recorded for this dataset.</p>;
  }

  return (
    <div>
      <div className="relative overflow-hidden rounded-lg border border-border bg-white" style={{ height: 480 }}>
        <div ref={holderRef} className="prov-graph h-full w-full" />
        <button
          type="button"
          onClick={() => {
            setTip(null);
            setShowAll((v) => !v);
          }}
          className="absolute right-3 top-3 rounded-md border border-border bg-white px-2.5 py-1 text-xs text-foreground shadow-sm hover:bg-muted"
        >
          {showAll ? 'Hide all details' : 'Show all details'}
        </button>
        {tip ? (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-border bg-white text-xs shadow-lg"
            style={{ left: tip.x + 14, top: tip.y + 14, minWidth: 150, padding: '6px 9px' }}
          >
            {tip.attrs.map((a) => (
              <div key={a.label} className="flex justify-between gap-3 py-0.5">
                <span className="text-neutral-500">{a.label}</span>
                <span className="font-mono text-neutral-800">{a.value}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <Legend />
    </div>
  );
}
