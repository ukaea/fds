import useSWRInfinite from 'swr/infinite';
import { fetcher } from '@/lib/api';
import { withQuery } from '@/lib/properties';

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
      return withQuery(url, `offset=${index * pageSize}`, `limit=${pageSize}`);
    },
    fetcher,
    { keepPreviousData: true, revalidateFirstPage: false }
  );

  const last = data?.[data.length - 1];
  return {
    items: data?.flat(),
    error,
    isLoading,
    done: !!last && last.length < pageSize,
    loadingMore: !!data && data.length < size,
    loadMore: () => setSize(size + 1),
  };
}
