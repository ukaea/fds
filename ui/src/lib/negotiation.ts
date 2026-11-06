// How an Accept header ranks two media types, by its q-values. FDS chooses
// between JSON and JSON-LD by the same rule.

type MediaRange = { range: string; quality: number };

// Each media range in an Accept header, with its q-value. A range whose q-value
// is not a number is left out.
function mediaRanges(accept: string): MediaRange[] {
  const ranges: MediaRange[] = [];
  for (const part of accept.split(',')) {
    const [range, ...parameters] = part.split(';').map((piece) => piece.trim());
    let quality = 1;
    for (const parameter of parameters) {
      const at = parameter.indexOf('=');
      const name = at < 0 ? parameter : parameter.slice(0, at);
      const value = at < 0 ? '' : parameter.slice(at + 1).trim();
      if (name.trim().toLowerCase() === 'q') {
        quality = value === '' ? NaN : Number(value);
      }
    }
    if (range && quality >= 0) {
      ranges.push({ range: range.toLowerCase(), quality });
    }
  }
  return ranges;
}

// The q-value an Accept header gives `mediaType`, and how closely the range it
// comes from names it. The most specific range that matches decides: the media
// type itself (2), then its type with any subtype, such as application/* (1),
// then */* (0). A media type no range matches has q-value 0 and closeness -1.
function preference(ranges: MediaRange[], mediaType: string): [number, number] {
  const kind = mediaType.split('/')[0];
  const closenessOf = new Map([
    [mediaType, 2],
    [`${kind}/*`, 1],
    ['*/*', 0],
  ]);
  let best: [number, number] = [0, -1];
  for (const { range, quality } of ranges) {
    const closeness = closenessOf.get(range) ?? -1;
    if (closeness > best[1]) best = [quality, closeness];
  }
  return best;
}

/**
 * Whether an Accept header prefers `wanted` to `other`. It does when it gives
 * `wanted` a higher q-value, or the same one while naming `wanted` itself. A
 * q-value of 0 means "not this", and a missing header prefers neither.
 */
export function prefers(accept: string | null, wanted: string, other: string): boolean {
  if (!accept) return false;
  const ranges = mediaRanges(accept);
  const [wantedQuality, wantedCloseness] = preference(ranges, wanted);
  const [otherQuality] = preference(ranges, other);
  if (wantedQuality <= 0) return false;
  return wantedQuality > otherQuality || (wantedQuality === otherQuality && wantedCloseness === 2);
}
