import type { Metadata } from 'next';

import ShotDetail from '@/components/detail/shot-detail';
import { fetchJsonLd, JsonLdScript, landingMetadata } from '@/lib/identifier-page';

type Params = { params: Promise<{ device: string; shot: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { device, shot } = await params;
  const path = `/devices/${device}/shots/${shot}`;
  return landingMetadata(await fetchJsonLd(path), path, `Shot ${shot}`);
}

export default async function ShotIdentifierPage({ params }: Params) {
  const { device, shot } = await params;

  return (
    <>
      <JsonLdScript document={await fetchJsonLd(`/devices/${device}/shots/${shot}`)} />
      <ShotDetail deviceName={device} shotId={shot} />
    </>
  );
}
