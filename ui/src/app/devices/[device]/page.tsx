import type { Metadata } from 'next';

import DeviceDetail from '@/components/detail/device-detail';
import { fetchJsonLd, JsonLdScript, landingMetadata } from '@/lib/identifier-page';

type Params = { params: Promise<{ device: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { device } = await params;
  return landingMetadata(await fetchJsonLd(`/devices/${device}`), `/devices/${device}`, device);
}

export default async function DeviceIdentifierPage({ params }: Params) {
  const { device } = await params;

  return (
    <>
      <JsonLdScript document={await fetchJsonLd(`/devices/${device}`)} />
      <DeviceDetail deviceName={device} />
    </>
  );
}
