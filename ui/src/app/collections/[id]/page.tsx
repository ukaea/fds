import type { Metadata } from 'next';

import CollectionDetail from '@/components/detail/collection-detail';
import { fetchJsonLd, JsonLdScript, landingMetadata } from '@/lib/identifier-page';

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  return landingMetadata(
    await fetchJsonLd(`/collections/${id}`),
    `/collections/${id}`,
    `Collection ${id}`
  );
}

export default async function CollectionIdentifierPage({ params }: Params) {
  const { id } = await params;

  return (
    <>
      <JsonLdScript document={await fetchJsonLd(`/collections/${id}`)} />
      <CollectionDetail id={id} />
    </>
  );
}
