import { signOut } from 'next-auth/react';

export const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    if (res.status === 401) {
      await signOut({ callbackUrl: '/' });
    }
    const errorBody = await res.text().catch(() => '');
    throw new Error(`An error occurred while fetching the data: ${res.status} ${res.statusText} ${errorBody}`);
  }
  return res.json();
};

// FDS serves the same resource as DCAT JSON-LD under content negotiation.
export const ldFetcher = async (url: string) => {
  const res = await fetch(url, { headers: { Accept: 'application/ld+json' } });
  if (!res.ok) {
    throw new Error(`Could not load JSON-LD: ${res.status} ${res.statusText}`);
  }
  return res.json();
};

export const API_BASE = '/api/v1';
