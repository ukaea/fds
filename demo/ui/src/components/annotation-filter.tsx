'use client';

import { AnnotationFacet, annotationToken } from '@/lib/features';

const PILL = 'text-xs px-2.5 py-1 rounded-full border transition-colors';
const IDLE = 'bg-card text-muted-foreground border-border hover:text-foreground hover:border-foreground/40';
const ACTIVE = 'bg-foreground text-background border-foreground';

function Pill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`${PILL} ${active ? ACTIVE : IDLE}`}
    >
      {label}
    </button>
  );
}

/**
 * Filter chips for one annotation parameter, built from the annotations present
 * on the records in scope rather than from a vocabulary.
 *
 * Every selected chip ANDs with the rest, which is what the server does with a
 * repeated parameter, including two values of the same property. Each annotation
 * is matched against the whole scientific_metadata list independently, so
 * confinement_mode:L-mode with confinement_mode:H-mode asks for a record holding
 * both entries: a shot that transitioned. Renders nothing when no record in
 * scope is annotated.
 */
export function AnnotationFilter({
  label,
  facets,
  selected,
  onChange,
}: {
  label: string;
  facets: AnnotationFacet[];
  selected: string[];
  onChange: (selected: string[]) => void;
}) {
  if (facets.length === 0) return null;

  const toggle = (token: string) => {
    onChange(
      selected.includes(token)
        ? selected.filter((t) => t !== token)
        : [...selected, token]
    );
  };

  return (
    <div className="card p-4 mb-6">
      <div className="flex items-baseline justify-between gap-4 mb-3">
        <p className="text-muted-foreground uppercase text-xs font-bold tracking-wider">{label}</p>
        {selected.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        )}
      </div>
      <div className="space-y-2">
        {facets.map((facet) => (
          <div key={facet.name} className="flex items-center gap-2 flex-wrap">
            <Pill
              label={facet.name}
              active={selected.includes(facet.name)}
              onClick={() => toggle(facet.name)}
            />
            {facet.values.map((value) => {
              const token = annotationToken(facet.name, value);
              return (
                <Pill
                  key={value}
                  label={value}
                  active={selected.includes(token)}
                  onClick={() => toggle(token)}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
