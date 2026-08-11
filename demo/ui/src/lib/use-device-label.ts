'use client';

import useSWR from 'swr';
import { fetcher, API_BASE } from '@/lib/api';
import { Device } from '@/lib/types';

/**
 * Display label for a device: its `title` when set, otherwise the `name` from
 * the URL. Device names are lower-cased identifiers (`mastu`), so pages show
 * the title (`MAST Upgrade`) instead. SWR caches by URL, so calling this from
 * several components on a page issues one request.
 */
export function useDeviceLabel(deviceName: string | undefined): string {
  const { data } = useSWR<Device>(
    deviceName ? `${API_BASE}/devices/${deviceName}` : null,
    fetcher
  );
  return data?.title || deviceName || '';
}
