import { API_BASE, fetcher } from './api';
import type {
  Activity,
  ActivityAgent,
  ActivityDelegation,
  Collection,
  Dataset,
  Source,
} from './types';

// A renderer-agnostic PROV-O lineage graph, walked upstream from a dataset or
// rooted at a collection.
export type ProvNodeKind =
  | 'dataset'
  | 'instrument'
  | 'activity'
  | 'agent'
  | 'collection';
export type ProvEdgeKind =
  | 'wasGeneratedBy'
  | 'used'
  | 'wasAssociatedWith'
  | 'actedOnBehalfOf'
  | 'hadMember';

export interface ProvAttr {
  label: string;
  value: string;
}

export interface ProvNode {
  id: string;
  kind: ProvNodeKind;
  label: string;
  sub?: string;
  // prov:* attributes shown in the hover-reveal box (type, version, times, …).
  attrs?: ProvAttr[];
}

export interface ProvEdge {
  id: string;
  source: string;
  target: string;
  kind: ProvEdgeKind;
  label?: string;
}

export interface ProvGraph {
  nodes: ProvNode[];
  edges: ProvEdge[];
}

// Guard against pathological depth; provenance is a DAG but be defensive.
const MAX_DEPTH = 8;

const AGENT_PROV_TYPE: Record<string, string> = {
  software: 'prov:SoftwareAgent',
  person: 'prov:Person',
  organization: 'prov:Organization',
};

// Shared machinery for building a PROV graph; the dataset and collection entry
// points below both drive the same walk. `sources` (fetched once by the caller)
// resolves every source id to a name/kind for the whole graph.
function createLineageWalker(sources: Source[]) {
  const sourceById = new Map<number, Source>(sources.map((s) => [s.id, s]));

  const nodes = new Map<string, ProvNode>();
  const edges = new Map<string, ProvEdge>();
  const seenDatasets = new Set<number>();
  const seenActivities = new Set<number>();

  const putNode = (n: ProvNode) => {
    if (!nodes.has(n.id)) nodes.set(n.id, n);
  };
  const putEdge = (e: ProvEdge) => {
    if (!edges.has(e.id)) edges.set(e.id, e);
  };

  // Create (once) the entity node for a dataset, without walking its lineage.
  const datasetNode = (ds: Dataset): string => {
    const dsAttrs: ProvAttr[] = [{ label: 'prov:type', value: 'dcat:Dataset' }];
    if (ds.level != null) dsAttrs.push({ label: 'level', value: String(ds.level) });
    if (ds.media_type) dsAttrs.push({ label: 'media type', value: ds.media_type });
    putNode({
      id: `dataset:${ds.id}`,
      kind: 'dataset',
      label: ds.name,
      sub: ds.level != null ? `level ${ds.level}` : undefined,
      attrs: dsAttrs,
    });
    return `dataset:${ds.id}`;
  };

  const agentNode = (sid: number): string => {
    const s = sourceById.get(sid);
    const kind: ProvNodeKind = s?.kind === 'instrument' ? 'instrument' : 'agent';
    const provType = s?.kind
      ? (AGENT_PROV_TYPE[s.kind] ?? 'prov:SoftwareAgent')
      : 'prov:SoftwareAgent';
    putNode({
      id: `source:${sid}`,
      kind,
      label: s?.name ?? `source ${sid}`,
      // Only surface a sub-line when the source declares a kind; unclassified
      // agents show just their name (no literal "agent").
      sub: s?.kind ?? undefined,
      attrs: [{ label: 'prov:type', value: provType }],
    });
    return `source:${sid}`;
  };

  async function walkDataset(ds: Dataset, depth: number): Promise<void> {
    if (ds.id == null || seenDatasets.has(ds.id)) return;
    seenDatasets.add(ds.id);
    datasetNode(ds);
    if (ds.activity_id == null || depth >= MAX_DEPTH) return;
    await walkActivity(ds.activity_id, `dataset:${ds.id}`, depth);
  }

  async function walkActivity(
    activityId: number,
    generatedNodeId: string,
    depth: number,
  ): Promise<void> {
    const aNodeId = `activity:${activityId}`;
    // The generated-by edge is per output dataset (an activity may make several).
    putEdge({
      id: `gen:${generatedNodeId}`,
      source: generatedNodeId,
      target: aNodeId,
      kind: 'wasGeneratedBy',
    });
    if (seenActivities.has(activityId)) return;
    seenActivities.add(activityId);

    const act: Activity = await fetcher(`${API_BASE}/activities/${activityId}`);
    const actAttrs: ProvAttr[] = [];
    if (act.activity_type) actAttrs.push({ label: 'prov:type', value: act.activity_type });
    if (act.source_version) actAttrs.push({ label: 'version', value: act.source_version });
    if (act.started_at) actAttrs.push({ label: 'startedAtTime', value: act.started_at });
    if (act.ended_at) actAttrs.push({ label: 'endedAtTime', value: act.ended_at });
    if (act.parameters) {
      for (const [k, v] of Object.entries(act.parameters)) {
        actAttrs.push({ label: k, value: String(v) });
      }
    }
    putNode({
      id: aNodeId,
      kind: 'activity',
      label: act.activity_type ?? 'activity',
      sub: act.source_version ?? undefined,
      attrs: actAttrs,
    });

    if (act.source_id != null) {
      putEdge({
        id: `assoc:${activityId}:${act.source_id}:executor`,
        source: aNodeId,
        target: agentNode(act.source_id),
        kind: 'wasAssociatedWith',
        label: 'executor',
      });
    }

    const agents: ActivityAgent[] = await fetcher(
      `${API_BASE}/activities/${activityId}/agents`,
    );
    for (const ag of agents) {
      putEdge({
        id: `assoc:${activityId}:${ag.source_id}:${ag.role}`,
        source: aNodeId,
        target: agentNode(ag.source_id),
        kind: 'wasAssociatedWith',
        label: ag.role,
      });
    }

    const instruments: Source[] = await fetcher(
      `${API_BASE}/activities/${activityId}/instruments`,
    );
    for (const ins of instruments) {
      putNode({
        id: `source:${ins.id}`,
        kind: 'instrument',
        label: ins.name,
        sub: 'instrument',
        attrs: [
          { label: 'prov:type', value: 'prov:Entity' },
          { label: 'kind', value: 'instrument' },
        ],
      });
      putEdge({
        id: `used:${activityId}:source:${ins.id}`,
        source: aNodeId,
        target: `source:${ins.id}`,
        kind: 'used',
        label: 'instrument',
      });
    }

    const delegations: ActivityDelegation[] = await fetcher(
      `${API_BASE}/activities/${activityId}/delegations`,
    );
    for (const d of delegations) {
      putEdge({
        id: `deleg:${activityId}:${d.subordinate_source_id}:${d.responsible_source_id}`,
        source: agentNode(d.subordinate_source_id),
        target: agentNode(d.responsible_source_id),
        kind: 'actedOnBehalfOf',
        label: 'on behalf of',
      });
    }

    const inputs: Dataset[] = await fetcher(
      `${API_BASE}/activities/${activityId}/inputs`,
    );
    for (const inp of inputs) {
      if (inp.id == null) continue;
      putEdge({
        id: `used:${activityId}:dataset:${inp.id}`,
        source: aNodeId,
        target: `dataset:${inp.id}`,
        kind: 'used',
        label: 'input',
      });
      await walkDataset(inp, depth + 1);
    }
  }

  return {
    putNode,
    putEdge,
    datasetNode,
    walkDataset,
    walkActivity,
    graph: (): ProvGraph => ({
      nodes: [...nodes.values()],
      edges: [...edges.values()],
    }),
  };
}

export async function buildLineage(datasetId: number): Promise<ProvGraph> {
  const sources: Source[] = await fetcher(`${API_BASE}/sources/`);
  const walker = createLineageWalker(sources);
  const root: Dataset = await fetcher(`${API_BASE}/datasets/id/${datasetId}`);
  await walker.walkDataset(root, 0);
  return walker.graph();
}

// A collection is the subject (a prov:Collection): its members hang off it via
// prov:hadMember, and its own producing activity is walked as lineage. Member
// datasets are leaf entities here; drill into a member for its full history.
export async function buildCollectionLineage(
  collection: Collection,
): Promise<ProvGraph> {
  const sources: Source[] = await fetcher(`${API_BASE}/sources/`);
  const walker = createLineageWalker(sources);

  const colNodeId = `collection:${collection.id}`;
  walker.putNode({
    id: colNodeId,
    kind: 'collection',
    label: collection.name,
    sub: 'collection',
    attrs: [{ label: 'prov:type', value: 'prov:Collection' }],
  });

  for (const ds of collection.datasets ?? []) {
    if (ds.id == null) continue;
    const memberId = walker.datasetNode(ds);
    walker.putEdge({
      id: `member:${colNodeId}:${memberId}`,
      source: colNodeId,
      target: memberId,
      kind: 'hadMember',
    });
  }

  for (const child of collection.child_collections ?? []) {
    if (child.id == null) continue;
    const childId = `collection:${child.id}`;
    walker.putNode({
      id: childId,
      kind: 'collection',
      label: child.name,
      sub: 'collection',
      attrs: [{ label: 'prov:type', value: 'prov:Collection' }],
    });
    walker.putEdge({
      id: `member:${colNodeId}:${childId}`,
      source: colNodeId,
      target: childId,
      kind: 'hadMember',
    });
  }

  if (collection.activity_id != null) {
    await walker.walkActivity(collection.activity_id, colNodeId, 0);
  }

  return walker.graph();
}
