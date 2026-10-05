import { Dataset } from '@/lib/types';

// Compact forms with a single canonical resolver, the same allowlist FDS uses
// in its JSON-LD. Anything else is shown as given rather than as a guessed link.
const RESOLVERS: [prefix: string, base: string][] = [
  ['doi:', 'https://doi.org/'],
  ['hdl:', 'https://hdl.handle.net/'],
  ['swh:', 'https://archive.softwareheritage.org/'],
];

export function resolveIdentifier(identifier: string): string | null {
  const value = identifier.trim();
  if (value.includes('://')) return value;
  const lower = value.toLowerCase();
  for (const [prefix, base] of RESOLVERS) {
    if (lower.startsWith(prefix)) {
      // swh: keeps its scheme in the path; doi: and hdl: do not.
      return base + (prefix === 'swh:' ? value : value.slice(prefix.length));
    }
  }
  return null;
}

// DataCite's recommended form: Creator (PublicationYear). Title. Version.
// Publisher. Identifier. A part the record lacks is left out rather than made up.
export function citation(dataset: Dataset): string | null {
  if (!dataset.persistent_identifier) return null;
  const identifier = resolveIdentifier(dataset.persistent_identifier) ?? dataset.persistent_identifier;
  const year = dataset.issued?.slice(0, 4);
  const lead = [dataset.creator, year && `(${year})`].filter(Boolean).join(' ');
  return [
    lead,
    dataset.title || dataset.name,
    dataset.version && `Version ${dataset.version}`,
    dataset.publisher,
    identifier,
  ]
    .filter(Boolean)
    .map((part) => String(part).replace(/\.$/, ''))
    .join('. ');
}
