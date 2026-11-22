'use client';

import { KeyboardEvent, ReactNode, useRef, useSyncExternalStore } from 'react';
import { Collection } from '@/lib/types';

const KEY_PREFIX = 'shot-collection-tab:';
const listeners = new Set<() => void>();
// Kept here too, for browsers that refuse storage: the open tab is then kept for
// as long as the page is open.
const memory = new Map<string, string>();

function storageKey(deviceName: string): string {
  return `${KEY_PREFIX}${deviceName}`;
}

// Another browser tab opening a Collection opens it here too.
function subscribe(listener: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key?.startsWith(KEY_PREFIX)) listener();
  };
  listeners.add(listener);
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}

function readOpen(deviceName: string): string {
  const key = storageKey(deviceName);
  try {
    return localStorage.getItem(key) ?? memory.get(key) ?? '';
  } catch {
    return memory.get(key) ?? '';
  }
}

function saveOpen(deviceName: string, name: string): void {
  const key = storageKey(deviceName);
  memory.set(key, name);
  try {
    localStorage.setItem(key, name);
  } catch {
    // Not remembered after the page closes, but kept for this one.
  }
  listeners.forEach((listener) => listener());
}

/**
 * A shot's Collections as tabs, in the order the catalogue lists them, one shown
 * at a time. The open tab is kept in this browser for the device, by Collection
 * name, so the next shot of the device opens on the same Collection when it has
 * one of that name, and on the first otherwise.
 */
export function CollectionTabs({
  deviceName,
  collections,
  children,
}: {
  deviceName: string;
  collections: Collection[];
  children: (collection: Collection) => ReactNode;
}) {
  // Empty on the server, which cannot know what this browser stored.
  const openName = useSyncExternalStore(subscribe, () => readOpen(deviceName), () => '');
  const open = collections.find((c) => c.name === openName) ?? collections[0];
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    const target = index + step;
    if (step === 0 || target < 0 || target >= collections.length) return;
    event.preventDefault();
    saveOpen(deviceName, collections[target].name);
    tabRefs.current[target]?.focus();
  }

  if (!open) return null;

  return (
    <div className="mb-10">
      <div
        role="tablist"
        aria-label="Collections"
        className="flex flex-wrap gap-1 border-b border-border mb-6"
      >
        {collections.map((collection, index) => {
          const selected = collection.id === open.id;
          const count = collection.datasets?.length ?? 0;
          return (
            <button
              key={collection.id}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`collection-tab-${collection.id}`}
              aria-selected={selected}
              aria-controls={`collection-panel-${collection.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => saveOpen(deviceName, collection.name)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={`px-4 py-2 -mb-px border-b-2 text-sm transition-colors ${
                selected
                  ? 'border-primary text-foreground font-semibold'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {collection.title || collection.name}
              <span className="ml-2 text-xs text-muted-foreground">{count}</span>
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`collection-panel-${open.id}`}
        aria-labelledby={`collection-tab-${open.id}`}
      >
        {children(open)}
      </div>
    </div>
  );
}
