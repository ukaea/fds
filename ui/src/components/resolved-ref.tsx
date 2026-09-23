'use client';

import Link from 'next/link';
import { Dataset } from '@/lib/types';
import { coverageSummary } from '@/lib/coverage';

// A resolved related dataset (geometry version, calibration version, or feature
// annotation) as a compact linked row. An annotation labels the feature it
// localises; a reference version labels the roles it provides.
export function ResolvedRef({ version }: { version: Dataset }) {
  const roles =
    version.geometry_roles ??
    version.calibration_roles ??
    (version.annotates ? [version.annotates] : []);
  const coverage = coverageSummary(version.applies_to);
  const inner = (
    <div className="bg-card border border-border rounded p-3 hover:border-primary/50 transition-colors">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-foreground">{version.name}</span>
        {version.calibration_stage != null && (
          <span className="text-xs text-muted-foreground shrink-0">stage {version.calibration_stage}</span>
        )}
      </div>
      {roles.length > 0 && <p className="text-xs text-muted-foreground mt-1">{roles.join(', ')}</p>}
      {coverage && <p className="text-xs text-muted-foreground font-mono mt-1">{coverage}</p>}
    </div>
  );
  if (!version.id) return inner;
  const href = `/datasets/${version.id}`;
  return (
    <Link href={href} className="block">
      {inner}
    </Link>
  );
}

// De-duplicate resolved versions by id, preserving order (stage order for a chain).
export function dedupeById(versions: Dataset[]): Dataset[] {
  const seen = new Set<number>();
  const out: Dataset[] = [];
  for (const v of versions) {
    if (v.id != null && seen.has(v.id)) continue;
    if (v.id != null) seen.add(v.id);
    out.push(v);
  }
  return out;
}
