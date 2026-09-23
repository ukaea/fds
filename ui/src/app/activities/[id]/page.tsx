import type { Metadata } from 'next';

import ActivityDetail from '@/components/detail/activity-detail';
import { fetchJsonLd, JsonLdScript, landingMetadata } from '@/lib/identifier-page';

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  return landingMetadata(await fetchJsonLd(`/activities/${id}`), `/activities/${id}`, `Activity ${id}`);
}

export default async function ActivityIdentifierPage({ params }: Params) {
  const { id } = await params;

  return (
    <>
      <JsonLdScript document={await fetchJsonLd(`/activities/${id}`)} />
      <ActivityDetail id={id} />
    </>
  );
}
