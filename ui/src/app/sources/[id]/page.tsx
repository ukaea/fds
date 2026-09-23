import type { Metadata } from 'next';

import SourceDetail from '@/components/detail/source-detail';
import { fetchJsonLd, JsonLdScript, landingMetadata } from '@/lib/identifier-page';

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  return landingMetadata(await fetchJsonLd(`/sources/${id}`), `/sources/${id}`, `Source ${id}`);
}

export default async function SourceIdentifierPage({ params }: Params) {
  const { id } = await params;

  return (
    <>
      <JsonLdScript document={await fetchJsonLd(`/sources/${id}`)} />
      <SourceDetail id={id} />
    </>
  );
}
