import { getSession, signOut } from 'next-auth/react';

// Carries the status so a caller can tell a missing record (404) from a
// restricted one (401 when not signed in, 403 when signed in) from a failure.
export class FetchError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

export const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    // FDS answers 401 both when a signed-in person's token no longer works and
    // when someone not signed in asks for a restricted record. Only the first
    // ends a session.
    if (res.status === 401 && (await getSession())) {
      await signOut({ callbackUrl: '/' });
    }
    const errorBody = await res.text().catch(() => '');
    throw new FetchError(
      res.status,
      `An error occurred while fetching the data: ${res.status} ${res.statusText} ${errorBody}`
    );
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

export { API_BASE } from '@/lib/api-version';
