'use client';

import { useEffect, useRef } from 'react';

/**
 * Fetches the next page as the end of a list comes into view.
 *
 * A button rather than a bare marker, so a keyboard user, or anyone whose
 * browser has no IntersectionObserver, can still ask for more.
 */
export function LoadMore({
  onLoad,
  loading,
  done,
}: {
  onLoad: () => void;
  loading: boolean;
  done: boolean;
}) {
  const ref = useRef<HTMLButtonElement>(null);

  // Re-observed after every page, so a page too short to push the button out of
  // view is followed by another rather than stalling.
  useEffect(() => {
    const element = ref.current;
    if (!element || done || loading || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && onLoad(),
      { rootMargin: '600px' }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [onLoad, loading, done]);

  if (done) return null;
  return (
    <button
      ref={ref}
      type="button"
      onClick={onLoad}
      disabled={loading}
      className="block mx-auto mt-6 text-sm px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground disabled:opacity-60 transition-colors"
    >
      {loading ? 'Loading more…' : 'Load more'}
    </button>
  );
}
