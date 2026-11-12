'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { Graphviz } from '@hpcc-js/wasm-graphviz';

import {
  buildCollectionLineage,
  buildLineage,
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
  wasDerivedFrom: 'wasDerivedFrom',
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

const EDGE_COLOR = '#555555';

function toDot(graph: ProvGraph): string {
  const L: string[] = ['digraph prov {'];
  // ranksep is modest because each edge carries an inline label node, which
  // adds an intermediate rank of its own.
  L.push('  rankdir=BT; bgcolor="transparent"; nodesep=0.4; ranksep=0.3;');
  // A single font Graphviz knows: given a list it does not recognise, it sizes
  // shapes for Times, and the wider Helvetica the browser draws spills out.
  L.push('  node [fontname="Helvetica", fontsize=11, penwidth=1.4];');
  L.push('  edge [fontname="Helvetica", color="#8a8a8a", arrowsize=0.7];');

  for (const n of graph.nodes) {
    L.push(`  "${n.id}" [${NODE_DOT[SHAPE_OF[n.kind]]}, label=${nodeLabel(n.label, n.sub)}];`);
  }

  for (const e of graph.edges) {
    // Carry the relation label on an inline node so it sits ON the edge (line
    // running through it), not offset to one side where it reads as belonging
    // to a neighbouring node.
    const el = `el:${e.id}`;
    // height=0.02 collapses the node to fit the text; without it the default
    // 0.5" minimum height leaves a big gap between the label and the edge line.
    L.push(`  "${el}" [shape=plaintext, margin=0.01, height=0.02, label=${edgeLabel(EDGE_LABEL[e.kind], EDGE_COLOR)}];`);
    L.push(`  "${e.source}" -> "${el}" [arrowhead=none];`);
    L.push(`  "${el}" -> "${e.target}";`);
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
      <span className="italic">click a node for its details</span>
    </div>
  );
}

const KIND_NAME: Record<ProvNodeKind, string> = {
  dataset: 'Dataset',
  instrument: 'Instrument',
  collection: 'Collection',
  activity: 'Activity',
  agent: 'Agent',
};

// The node's own page: a path on this site, another site's address, or none
// for an upstream known only by its description.
function pageOf(id: string): { href: string; internal: boolean } | null {
  try {
    const url = new URL(id);
    if (url.origin === window.location.origin) return { href: url.pathname, internal: true };
    return /^https?:$/.test(url.protocol) ? { href: url.href, internal: false } : null;
  } catch {
    return null;
  }
}

function DetailPanel({
  graph,
  nodeId,
  onSelect,
}: {
  graph: ProvGraph;
  nodeId: string | null;
  onSelect: (id: string) => void;
}) {
  const node = nodeId ? graph.nodes.find((n) => n.id === nodeId) : undefined;
  if (!node) {
    return <p className="text-sm text-muted-foreground">Click a node to see its details.</p>;
  }
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const relations = graph.edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => {
      const outgoing = e.source === node.id;
      return { edge: e, outgoing, other: byId.get(outgoing ? e.target : e.source) };
    });
  const page = pageOf(node.id);

  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {KIND_NAME[node.kind]}
          {node.sub ? ` · ${node.sub}` : ''}
        </p>
        <h3 className="font-medium text-foreground break-words">{node.label}</h3>
      </div>
      {node.attrs?.length ? (
        <dl className="space-y-2">
          {node.attrs.map((a) => (
            <div key={a.label}>
              <dt className="text-xs text-muted-foreground">{a.label}</dt>
              <dd className="font-mono text-xs text-foreground break-all">{a.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {relations.length ? (
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Relations</p>
          <ul className="space-y-1">
            {relations.map(({ edge, outgoing, other }) => (
              <li key={edge.id} className="text-xs">
                <span className="text-muted-foreground">
                  {outgoing ? EDGE_LABEL[edge.kind] : `${EDGE_LABEL[edge.kind]} by`}
                </span>{' '}
                <button
                  type="button"
                  onClick={() => other && onSelect(other.id)}
                  className="text-foreground underline decoration-dotted underline-offset-2 hover:decoration-solid break-all text-left"
                >
                  {other?.label ?? (outgoing ? edge.target : edge.source)}
                </button>
                {edge.label ? <span className="text-muted-foreground"> · {edge.label}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {page ? (
        page.internal ? (
          <Link href={page.href} className="inline-block text-xs underline underline-offset-2">
            Open {KIND_NAME[node.kind].toLowerCase()} page
          </Link>
        ) : (
          <a href={page.href} target="_blank" rel="noopener noreferrer" className="inline-block text-xs underline underline-offset-2">
            Open at its source
          </a>
        )
      ) : null}
    </div>
  );
}

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

  const [renderError, setRenderError] = useState(false);
  const holderRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const selectedRef = useRef<string | null>(null);

  // Outline the selected node. The SVG is rebuilt only when the data changes,
  // so this runs again after each render as well as on each selection.
  const highlight = () => {
    holderRef.current?.querySelectorAll('g.node').forEach((g) => {
      g.classList.toggle('selected', g.querySelector('title')?.textContent === selectedRef.current);
    });
  };
  const select = (id: string) => {
    selectedRef.current = id;
    setSelected(id);
    highlight();
  };

  useEffect(() => {
    if (!data || !holderRef.current) return;
    const holder = holderRef.current;
    let cancelled = false;
    const cleanups: Array<() => void> = [];
    let dragging = false;
    let moved = false;
    let px = 0;
    let py = 0;

    (async () => {
      try {
        const gv = await loadGraphviz();
        if (cancelled) return;
        holder.innerHTML = gv.dot(toDot(data));
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
            // A large graph is fitted small, so a limit relative to the fit alone
            // stops short of readable text; also allow up to 4 px per point.
            const minW = Math.min(baseW * 0.1, r.width / 4);
            if (w * f < minW || w * f > baseW * 2) return;
            x = mx - (mx - x) * f;
            y = my - (my - y) * f;
            w *= f;
            h *= f;
            apply();
          };
          const onDown = (e: MouseEvent) => {
            dragging = true;
            moved = false;
            px = e.clientX;
            py = e.clientY;
            svg.style.cursor = 'grabbing';
          };
          const onMove = (e: MouseEvent) => {
            if (!dragging) return;
            const r = svg.getBoundingClientRect();
            x -= ((e.clientX - px) / r.width) * w;
            y -= ((e.clientY - py) / r.height) * h;
            if (Math.abs(e.clientX - px) + Math.abs(e.clientY - py) > 2) moved = true;
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

        // Every PROV node selects on click or Enter; the edge-label nodes do not.
        const byId = new Map(data.nodes.map((n) => [n.id, n]));
        holder.querySelectorAll('g.node').forEach((g) => {
          const id = g.querySelector('title')?.textContent ?? '';
          const node = byId.get(id);
          if (!node) return;
          g.classList.add('selectable');
          g.setAttribute('tabindex', '0');
          g.setAttribute('role', 'button');
          g.setAttribute('aria-label', `${node.label}, show details`);
          g.addEventListener('click', () => {
            if (!moved) select(id);
          });
          g.addEventListener('keydown', (ev) => {
            const key = (ev as KeyboardEvent).key;
            if (key === 'Enter' || key === ' ') {
              ev.preventDefault();
              select(id);
            }
          });
        });
        highlight();
      } catch {
        if (!cancelled) setRenderError(true);
      }
    })();

    return () => {
      cancelled = true;
      cleanups.forEach((c) => c());
    };
    // highlight and select read refs, so they need not re-run the render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

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
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="relative overflow-hidden rounded-lg border border-border bg-white" style={{ height: 480 }}>
          <div ref={holderRef} className="prov-graph h-full w-full" />
        </div>
        <aside
          aria-label="Selected node"
          className="rounded-lg border border-border p-3 lg:h-[480px] lg:overflow-y-auto"
        >
          <DetailPanel graph={data} nodeId={selected} onSelect={select} />
        </aside>
      </div>
      <Legend />
    </div>
  );
}
