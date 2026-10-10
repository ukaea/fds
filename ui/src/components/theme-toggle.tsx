'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { Moon, Sun, SunMoon } from 'lucide-react';
import {
  THEME_KEY,
  ThemePreference,
  applyTheme,
  readPreference,
  watchSystemTheme,
} from '@/lib/theme';

const listeners = new Set<() => void>();

// Another tab changing the theme changes this one too.
function subscribe(listener: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== THEME_KEY) return;
    applyTheme(readPreference());
    listener();
  };
  listeners.add(listener);
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}

// The same cycle and icons as the documentation site's switch: the icon shows
// the current choice, the label names the next.
const NEXT: Record<ThemePreference, ThemePreference> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
};
const ICON = { system: SunMoon, light: Sun, dark: Moon };
const LABEL = { system: 'system preference', light: 'light mode', dark: 'dark mode' };

export function ThemeToggle() {
  // Null on the server, which cannot know what this browser stored.
  const preference = useSyncExternalStore(subscribe, readPreference, () => null);

  useEffect(() => {
    if (preference !== 'system') return;
    return watchSystemTheme(() => applyTheme('system'));
  }, [preference]);

  // Holds the button's place until the stored choice is known, so the header
  // does not shift when it appears.
  if (!preference) return <span className="w-8 h-8" aria-hidden />;

  const next = NEXT[preference];
  const Icon = ICON[preference];
  const choose = () => {
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // Not remembered, but still applied for this page.
    }
    applyTheme(next);
    listeners.forEach((listener) => listener());
  };

  return (
    <button
      type="button"
      onClick={choose}
      title={`Switch to ${LABEL[next]}`}
      aria-label={`Theme: ${LABEL[preference]}. Switch to ${LABEL[next]}`}
      className="w-8 h-8 flex items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
    >
      <Icon className="w-4 h-4" />
    </button>
  );
}
