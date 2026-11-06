'use client';

import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { AvailableProperties } from '@/lib/types';
import { pickedPaths, picksWithout, Possible, Ranges, withQuery } from '@/lib/properties';

/**
 * What remains possible in a panel backed by a properties endpoint.
 *
 * One summary with every pick, read by the rows that have none, and one for
 * each row that has picks, leaving that row's own out. `summaryUrl` builds the
 * endpoint's url for a set of picks. `include_constant` keeps the properties
 * every record in scope holds with one value, which the endpoint otherwise
 * leaves out and which are exactly what a narrow scope tends to hold.
 *
 * Undefined with no picks, and while the first answer is on its way. Later
 * answers replace earlier ones only when they arrive, so options do not flash
 * back on between clicks.
 */
export function usePossible(
  summaryUrl: (tokens: string[], ranges: Ranges) => string | null,
  tokens: string[],
  ranges: Ranges = {}
): Possible | undefined {
  const picked = pickedPaths(tokens, ranges);
  const urls = [
    summaryUrl(tokens, ranges),
    ...picked.map((path) => {
      const others = picksWithout(path, tokens, ranges);
      return summaryUrl(others.tokens, others.ranges);
    }),
  ];
  const keys =
    picked.length > 0 && urls.every((url) => url !== null)
      ? urls.map((url) => withQuery(url as string, 'include_constant=true'))
      : null;

  const { data } = useSWR(
    keys,
    async (urlsToFetch: string[]) => {
      const [all, ...own] = await Promise.all(
        urlsToFetch.map((url) => fetcher(url) as Promise<AvailableProperties>)
      );
      return { all, own: Object.fromEntries(picked.map((path, i) => [path, own[i]])) };
    },
    { keepPreviousData: true }
  );

  if (!keys || !data) return undefined;
  return (name) => {
    const summary = data.own[name] ?? data.all;
    const entry = summary.properties.find((property) => property.name === name);
    if (!entry) return null;
    return { values: entry.values, min: entry.min, max: entry.max };
  };
}
