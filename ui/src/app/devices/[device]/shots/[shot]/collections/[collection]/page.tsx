import { notFound, redirect } from 'next/navigation';

import { fetchJson } from '@/lib/identifier-page';

type Params = { params: Promise<{ device: string; shot: string; collection: string }> };

// Keyed by name within a shot, so it has to resolve the collection before it can
// send the caller to the identifier that names it.
export default async function CollectionInShotPage({ params }: Params) {
  const { device, shot, collection } = await params;

  const record = await fetchJson<{ id?: number }>(
    `/v1/devices/${device}/shots/${shot}/collections/${collection}`
  );
  if (record?.id == null) notFound();

  redirect(`/collections/${record.id}`);
}
