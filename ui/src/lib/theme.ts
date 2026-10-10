export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_KEY = 'theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

// The palette follows `data-theme` on <html>, always resolved to light or dark,
// so the stylesheet defines the dark palette once rather than once for the
// media query and again for an explicit choice.
export function applyTheme(preference: ThemePreference): void {
  const dark =
    preference === 'dark' ||
    (preference === 'system' && window.matchMedia(DARK_QUERY).matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

export function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    // Storage is refused in some private modes; follow the system then.
    return 'system';
  }
}

// applyTheme(readPreference()), inlined in <head> so the palette is set before
// the first paint: run after hydration, a reader who chose light on a dark
// system would see the page flash dark on every load. Keep the two in step.
export const THEME_SCRIPT = `(function(){try{var p=localStorage.getItem('${THEME_KEY}');var d=p==='dark'||(p!=='light'&&matchMedia('${DARK_QUERY}').matches);document.documentElement.dataset.theme=d?'dark':'light'}catch(e){}})()`;

export function watchSystemTheme(onChange: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}
