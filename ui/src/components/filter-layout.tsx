/**
 * Filters in a column beside the results, held in view as the results scroll.
 *
 * Below `lg` there is no room for a column, so the filters sit above the
 * results as before. The column scrolls on its own when the filters outgrow the
 * window; the offset clears the sticky site header. With no filters to show
 * the results take the full width rather than sit beside an empty column.
 */
export function FilterLayout({
  filters,
  children,
}: {
  filters: React.ReactNode;
  children: React.ReactNode;
}) {
  if (!filters) return <div>{children}</div>;
  return (
    <div className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)] lg:gap-8 lg:items-start">
      {/* Padded and pulled back by the same amount: a scrolling box clips at its
          edge, and a card lifts 2px and casts a shadow on hover. */}
      <aside className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:-m-3 lg:p-3">
        {filters}
      </aside>
      <div>{children}</div>
    </div>
  );
}
