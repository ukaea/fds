import { Coverage } from './types';

// A compact one-line summary of a version's coverage — stays small even for
// hundreds of shots (explicit-shot sets collapse to a count + span).
export function coverageSummary(coverage?: Coverage): string | null {
  if (!coverage) return null;
  const parts: string[] = [];
  coverage.shot_ranges?.forEach((r) => parts.push(`${r.from_shot}→${r.to_shot ?? 'open'}`));
  coverage.date_ranges?.forEach((r) =>
    parts.push(`${r.from_date.slice(0, 10)}→${r.to_date ? r.to_date.slice(0, 10) : 'open'}`)
  );
  if (coverage.shots?.length) {
    const s = coverage.shots;
    parts.push(s.length <= 3 ? s.join(', ') : `${s.length} shots (${s[0]}…${s[s.length - 1]})`);
  }
  return parts.length ? parts.join('; ') : null;
}
