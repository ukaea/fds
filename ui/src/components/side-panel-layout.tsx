/**
 * A column beside the main content, held in view as the content scrolls: the
 * filters, and what describes the record rather than listing its contents.
 *
 * Below `lg` there is no room for a column, so it sits above the content. The
 * column scrolls on its own when it outgrows the window; the offset clears the
 * sticky site header. With nothing to put in it the content takes the full
 * width rather than sit beside an empty column.
 */
export function SidePanelLayout({
  side,
  children,
}: {
  side: React.ReactNode;
  children: React.ReactNode;
}) {
  if (!side) return <div>{children}</div>;
  return (
    <div className="lg:grid lg:grid-cols-[22rem_minmax(0,1fr)] lg:gap-8 lg:items-start">
      {/* Padded and pulled back by the same amount: a scrolling box clips at its
          edge, and a card lifts 2px and casts a shadow on hover. */}
      <aside className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:-m-3 lg:p-3">
        {side}
      </aside>
      <div>{children}</div>
    </div>
  );
}
