import { notFound, redirect } from 'next/navigation';

import { fetchJson } from '@/lib/identifier-page';

type Params = { params: Promise<{ device: string; shot: string; collection: string }> };

// Keyed by name within a shot, so it has to resolve the collection before it can
// send the caller to the identifier that names it.
export default async function CollectionInShotPage({ params }: Params) {
  const { device, shot, collection } = await params;

  const page = await fetchJson<{ id?: number }[]>(
    `/devices/${device}/shots/${shot}/collections?name=${encodeURIComponent(collection)}`
  );
  const id = page?.[0]?.id;
  if (id == null) notFound();

  redirect(`/collections/${id}`);
}
