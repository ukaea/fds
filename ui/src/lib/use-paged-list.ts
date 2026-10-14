import useSWRInfinite from 'swr/infinite';
import { fetcher } from '@/lib/api';
import { withQuery } from '@/lib/properties';

// The url of one page, which is also the key SWR caches it under. A caller
// prefetching a page builds its url here so the hook finds the prefetch.
export function pageUrl(url: string, index: number, pageSize: number): string {
  return withQuery(url, `offset=${index * pageSize}`, `limit=${pageSize}`);
}

/**
 * A listing read one page at a time and accumulated, for endless scroll.
 *
 * A short page is the end. The listings return no total, and a caller that has
 * one (the shot count) has it for the whole filter rather than for what has
 * loaded, so the page length is the only signal that works for every list.
 *
 * Changing `url` starts again from the first page: SWR keys the pages on it, so
 * a new filter cannot inherit the old filter's depth.
 */
export function usePagedList<T>(url: string | null, pageSize: number) {
  const { data, error, isLoading, size, setSize } = useSWRInfinite<T[]>(
    (index, previous: T[] | null) => {
      if (!url || (previous && previous.length < pageSize)) return null;
      return pageUrl(url, index, pageSize);
    },
    fetcher,
    { keepPreviousData: true, revalidateFirstPage: false }
  );

  const last = data?.[data.length - 1];
  const done = !!last && last.length < pageSize;
  return {
    items: data?.flat(),
    error,
    isLoading,
    done,
    loadingMore: !!data && data.length < size,
    // Asks for another page only once every page asked for so far has arrived.
    // A LoadMore already in view calls this on every render, and each call
    // restarts the fetch, so before the first page arrived a slow API never
    // answered in time and the list was requested without end.
    loadMore: () => {
      if (data && data.length === size && !done) setSize(size + 1);
    },
  };
}
