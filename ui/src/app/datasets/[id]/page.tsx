import type { Metadata } from 'next';

import DatasetDetail from '@/components/detail/dataset-detail';
import { fetchJsonLd, JsonLdScript, landingMetadata } from '@/lib/identifier-page';

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  return landingMetadata(await fetchJsonLd(`/datasets/${id}`), `/datasets/${id}`, `Dataset ${id}`);
}

export default async function DatasetIdentifierPage({ params }: Params) {
  const { id } = await params;
  const document = await fetchJsonLd(`/datasets/${id}`);

  return (
    <>
      <JsonLdScript document={document} />
      <DatasetDetail id={id} jsonLd={document} />
    </>
  );
}
