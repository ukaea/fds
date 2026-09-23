import type { Metadata } from 'next';

import { auth } from '@/auth';

export type JsonLd = Record<string, unknown>;

async function get(path: string, accept: string): Promise<Response | null> {
  const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
  const session = await auth();

  const headers: Record<string, string> = { Accept: accept };
  if (session?.accessToken) {
    headers.Authorization = `Bearer ${session.accessToken}`;
  }

  try {
    const response = await fetch(`${backend}${path}`, { headers, cache: 'no-store' });
    return response.ok ? response : null;
  } catch {
    return null;
  }
}

/** One record from the versioned API, for a page that has to resolve a name to an id. */
export async function fetchJson<T>(path: string): Promise<T | null> {
  const response = await get(path, 'application/json');
  return response ? ((await response.json()) as T) : null;
}

/**
 * The JSON-LD FDS publishes for one of its identifiers, fetched server side so
 * it can go into the page itself. Null when the identifier does not resolve for
 * this caller, which includes a record they may not read.
 */
export async function fetchJsonLd(path: string): Promise<JsonLd | null> {
  const response = await get(path, 'application/ld+json');
  return response ? ((await response.json()) as JsonLd) : null;
}

function firstString(document: JsonLd | null, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = document?.[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return undefined;
}

/**
 * What a DOI registry, a crawler or a pasted link shows for this identifier.
 * `canonical` is the identifier itself, so the browsing route rendering the
 * same thing does not compete with it.
 */
export function landingMetadata(
  document: JsonLd | null,
  path: string,
  fallbackTitle: string
): Metadata {
  const title = firstString(document, ['title', 'dct:title', 'name']) ?? fallbackTitle;
  const description = firstString(document, ['description', 'dct:description']);

  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, type: 'article' },
  };
}

/**
 * The published JSON-LD, embedded in the page. This is what makes the landing
 * page machine-readable without a second request, which is what DOI registries
 * and dataset search engines look for.
 */
export function JsonLdScript({ document }: { document: JsonLd | null }) {
  if (!document) return null;

  // JSON.stringify will happily emit "</script>" and end the element early.
  const serialised = JSON.stringify(document).replace(/</g, '\\u003c');

  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serialised }} />;
}
