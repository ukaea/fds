import { ldFetcher } from './api';
import type { Collection } from './types';

// A renderer-agnostic PROV-O lineage graph, walked upstream from a dataset or
// rooted at a collection. It is read from the JSON-LD FDS publishes, so the
// graph shows exactly what a harvester receives and nothing else.
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
  | 'hadMember'
  | 'wasDerivedFrom';

export interface ProvAttr {
  label: string;
  value: string;
}

export interface ProvNode {
  id: string;
  kind: ProvNodeKind;
  label: string;
  sub?: string;
  // The node's own statements, shown in the hover-reveal box.
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

type Ld = Record<string, unknown>;

const AGENT_KIND: Record<string, string> = {
  'prov:SoftwareAgent': 'software',
  'prov:Person': 'person',
  'prov:Organization': 'organization',
};

// Every @id FDS publishes is answered by the UI's identifier route, so the
// address is all that is needed to follow one.
async function fetchLd(id: string): Promise<Ld | null> {
  try {
    return (await ldFetcher(`/api/identifiers${new URL(id).pathname}`)) as Ld;
  } catch {
    return null;
  }
}

// The resource a document is about, without FDS's catalogue record of it.
function resourceOf(document: Ld): Ld {
  const graph = document['@graph'];
  if (!Array.isArray(graph)) return document;
  return (graph.find((n: Ld) => n['@type'] !== 'dcat:CatalogRecord') as Ld | undefined) ?? document;
}

function list(value: unknown): Ld[] {
  if (Array.isArray(value)) return value as Ld[];
  return value && typeof value === 'object' ? [value as Ld] : [];
}

// A plain or typed literal as text.
function text(value: unknown): string | undefined {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value && typeof value === 'object' && '@value' in value) return String((value as Ld)['@value']);
  return undefined;
}

function typeOf(node: Ld): string | undefined {
  const t = node['@type'];
  return Array.isArray(t) ? t.map(String).join(', ') : text(t);
}

function titleOf(node: Ld): string | undefined {
  return text(node['title']) ?? text(node['dct:title']);
}

// "fuel:executor" or a full IRI, as its last segment.
function localName(iri: string | undefined): string | undefined {
  return iri?.split(/[:#/]/).pop();
}

function refId(value: unknown): string | undefined {
  return text((value as Ld | undefined)?.['@id']);
}

// An FDS dataset, as opposed to an upstream held somewhere else: same service,
// and a dataset's path.
function isFdsDataset(id: string, from: string): boolean {
  try {
    const url = new URL(id);
    return url.origin === new URL(from).origin && /^\/datasets\/\d+$/.test(url.pathname);
  } catch {
    return false;
  }
}

function attr(attrs: ProvAttr[], label: string, value: string | undefined) {
  if (value) attrs.push({ label, value });
}

function createLineageWalker() {
  const nodes = new Map<string, ProvNode>();
  const edges = new Map<string, ProvEdge>();
  const seenDatasets = new Set<string>();
  const seenActivities = new Set<string>();

  const putNode = (n: ProvNode) => {
    if (!nodes.has(n.id)) nodes.set(n.id, n);
  };
  const putEdge = (e: ProvEdge) => {
    if (!edges.has(e.id)) edges.set(e.id, e);
  };

  // The entity node for a dataset, from its document or, when that cannot be
  // read, from the reference that pointed at it.
  const datasetNode = (id: string, node: Ld, sub?: string): string => {
    const attrs: ProvAttr[] = [];
    attr(attrs, 'prov:type', typeOf(node) ?? 'dcat:Dataset');
    attr(attrs, 'identifier', text(node['identifier']));
    for (const pid of list(node['adms:identifier'])) attr(attrs, 'persistent identifier', text(pid['skos:notation']));
    attr(attrs, 'issued', text(node['dct:issued']));
    attr(attrs, 'generatedAtTime', text(node['prov:generatedAtTime']));
    const mediaTypes = list(node['dcat:distribution'])
      .map((d) => text(d['dcat:mediaType']))
      .filter((m): m is string => Boolean(m));
    attr(attrs, 'media type', [...new Set(mediaTypes)].join(', '));
    putNode({ id, kind: 'dataset', label: titleOf(node) ?? `dataset ${localName(id) ?? id}`, sub, attrs });
    return id;
  };

  const agentNode = (node: Ld): string => {
    const id = refId(node) ?? `agent:${titleOf(node)}`;
    const type = typeOf(node);
    const attrs: ProvAttr[] = [];
    attr(attrs, 'prov:type', type);
    for (const pid of list(node['adms:identifier'])) attr(attrs, 'persistent identifier', text(pid['skos:notation']));
    putNode({
      id,
      kind: 'agent',
      label: titleOf(node) ?? localName(id) ?? id,
      sub: type ? AGENT_KIND[type] : undefined,
      attrs,
    });
    return id;
  };

  async function walkDataset(id: string, depth: number, reference: Ld = {}): Promise<void> {
    if (seenDatasets.has(id)) return;
    seenDatasets.add(id);
    const document = await fetchLd(id);
    const node = document ? resourceOf(document) : reference;
    // A dataset the viewer may not read is drawn from the reference to it alone.
    datasetNode(id, node, document ? undefined : 'not readable');
    const activity = node['prov:wasGeneratedBy'] as Ld | undefined;
    if (activity && depth < MAX_DEPTH) await walkActivity(activity, id, depth);

    // Asserted lineage: an FDS upstream is followed like an input; anything
    // else is drawn as far as the record identifies it, and goes no further.
    const upstreams = list(node['prov:wasDerivedFrom']);
    for (const [i, upstream] of upstreams.entries()) {
      const upstreamId = refId(upstream);
      let target: string;
      if (upstreamId && isFdsDataset(upstreamId, id)) {
        if (depth >= MAX_DEPTH) continue;
        await walkDataset(upstreamId, depth + 1, upstream);
        target = upstreamId;
      } else {
        target = upstreamId ?? `upstream:${id}:${i}`;
        const attrs: ProvAttr[] = [{ label: 'prov:type', value: 'prov:Entity' }];
        attr(attrs, 'identifier', upstreamId ?? text(upstream['dct:identifier']));
        attr(attrs, 'description', text(upstream['dct:description']));
        putNode({
          id: target,
          kind: 'dataset',
          label: titleOf(upstream) ?? text(upstream['dct:identifier']) ?? upstreamId ?? 'undescribed upstream',
          sub: 'external',
          attrs,
        });
      }
      putEdge({ id: `derived:${id}:${target}`, source: id, target, kind: 'wasDerivedFrom' });
    }
  }

  async function walkActivity(activity: Ld, generatedId: string, depth: number): Promise<void> {
    const id = refId(activity) ?? `activity:${generatedId}`;
    // The generated-by edge is per output (an activity may make several).
    putEdge({ id: `gen:${generatedId}`, source: generatedId, target: id, kind: 'wasGeneratedBy' });
    if (seenActivities.has(id)) return;
    seenActivities.add(id);

    const associations = list(activity['prov:qualifiedAssociation']);
    const executor = associations.find((a) => localName(refId(a['prov:hadRole'])) === 'executor');
    const version = text((executor?.['prov:hadPlan'] as Ld | undefined)?.['dcat:version']);

    const attrs: ProvAttr[] = [];
    attr(attrs, 'prov:type', text(activity['prov:type']));
    attr(attrs, 'version', version);
    attr(attrs, 'startedAtTime', text(activity['prov:startedAtTime']));
    attr(attrs, 'endedAtTime', text(activity['prov:endedAtTime']));
    const parameters = activity['prov:value'];
    if (parameters && typeof parameters === 'object' && !Array.isArray(parameters)) {
      for (const [k, v] of Object.entries(parameters)) attr(attrs, k, text(v) ?? JSON.stringify(v));
    }
    putNode({
      id,
      kind: 'activity',
      label: text(activity['prov:type']) ?? 'activity',
      sub: version,
      attrs,
    });

    // An association may give only the agent's @id; its description is then on
    // the activity's prov:wasAssociatedWith.
    const described = new Map(
      list(activity['prov:wasAssociatedWith']).map((a) => [refId(a), a] as const),
    );
    const agents = associations.length
      ? associations.map((a) => ({ agent: a['prov:agent'] as Ld, role: localName(refId(a['prov:hadRole'])) }))
      : [...described.values()].map((agent) => ({ agent, role: undefined }));
    const placed: { agentId: string; full: Ld }[] = [];
    for (const { agent, role } of agents) {
      const full = (agent?.['@type'] ? agent : described.get(refId(agent))) ?? agent;
      if (!full) continue;
      const agentId = agentNode(full);
      placed.push({ agentId, full });
      putEdge({
        id: `assoc:${id}:${agentId}:${role ?? ''}`,
        source: id,
        target: agentId,
        kind: 'wasAssociatedWith',
        label: role,
      });
    }
    // After every agent is placed, so an agent acted for is drawn from its own
    // description rather than a bare placeholder.
    for (const { agentId, full } of placed) {
      for (const responsible of list(full['prov:actedOnBehalfOf'])) {
        const responsibleId = refId(responsible);
        if (!responsibleId) continue;
        putNode({ id: responsibleId, kind: 'agent', label: localName(responsibleId) ?? responsibleId });
        putEdge({
          id: `deleg:${agentId}:${responsibleId}`,
          source: agentId,
          target: responsibleId,
          kind: 'actedOnBehalfOf',
          label: 'on behalf of',
        });
      }
    }

    const usages = list(activity['prov:qualifiedUsage']);
    const used = usages.length
      ? usages.map((u) => ({ entity: u['prov:entity'] as Ld, role: localName(refId(u['prov:hadRole'])) }))
      : list(activity['prov:used']).map((entity) => ({ entity, role: 'input' }));
    for (const { entity, role } of used) {
      const entityId = refId(entity);
      if (!entityId) continue;
      if (role === 'instrument') {
        const attrs: ProvAttr[] = [{ label: 'prov:type', value: 'prov:Entity' }];
        putNode({ id: entityId, kind: 'instrument', label: titleOf(entity) ?? localName(entityId) ?? entityId, sub: 'instrument', attrs });
      } else {
        await walkDataset(entityId, depth + 1, entity);
      }
      putEdge({
        id: `used:${id}:${entityId}`,
        source: id,
        target: entityId,
        kind: 'used',
        label: role,
      });
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
  const walker = createLineageWalker();
  // Any absolute base will do: only the path is followed.
  await walker.walkDataset(`${window.location.origin}/datasets/${datasetId}`, 0);
  return walker.graph();
}

// A collection is the subject (a prov:Collection): its members hang off it via
// prov:hadMember, and its own producing activity is walked as lineage. Member
// datasets are leaf entities here; drill into a member for its full history.
export async function buildCollectionLineage(collection: Collection): Promise<ProvGraph> {
  const walker = createLineageWalker();
  const document = await fetchLd(`${window.location.origin}/collections/${collection.id}`);
  const node = document ? resourceOf(document) : {};
  const id = refId(node) ?? `collection:${collection.id}`;

  walker.putNode({
    id,
    kind: 'collection',
    label: titleOf(node) ?? collection.name,
    sub: 'collection',
    attrs: [{ label: 'prov:type', value: typeOf(node) ?? 'prov:Collection' }],
  });

  for (const member of list(node['dcat:dataset'])) {
    const memberId = refId(member);
    if (!memberId) continue;
    walker.datasetNode(memberId, member);
    walker.putEdge({ id: `member:${id}:${memberId}`, source: id, target: memberId, kind: 'hadMember' });
  }

  for (const child of list(node['dcat:catalog'])) {
    const childId = refId(child);
    if (!childId) continue;
    walker.putNode({
      id: childId,
      kind: 'collection',
      label: titleOf(child) ?? localName(childId) ?? childId,
      sub: 'collection',
      attrs: [{ label: 'prov:type', value: 'prov:Collection' }],
    });
    walker.putEdge({ id: `member:${id}:${childId}`, source: id, target: childId, kind: 'hadMember' });
  }

  const activity = node['prov:wasGeneratedBy'] as Ld | undefined;
  if (activity) await walker.walkActivity(activity, id, 0);

  return walker.graph();
}
