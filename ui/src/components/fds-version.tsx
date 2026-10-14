'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';

/**
 * The version of the FDS serving this UI's data, such as "v0.0.9", after an
 * optional prefix. Renders nothing until the version is known, or if FDS does
 * not answer.
 */
export function FdsVersion({ prefix = '', className }: { prefix?: string; className?: string }) {
  const { data } = useSWR<{ version: string | null }>('/api/version', fetcher, {
    revalidateOnFocus: false,
  });
  if (!data?.version) return null;
  return (
    <span className={className}>
      {prefix}v{data.version}
    </span>
  );
}
