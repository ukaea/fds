'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { Check, ChevronDown, ChevronRight, Copy } from 'lucide-react';
import { ldFetcher } from '@/lib/api';

/**
 * The record as FDS publishes it to the semantic web, on the page about it.
 *
 * Same URL as the page, asked for as `application/ld+json`: this is the
 * document a harvester receives, not a rendering of one, so what you copy is
 * what FDS serves. Fetched only when opened, since most visits will not want
 * it.
 */
export function JsonLdPanel({
  url,
  document,
  label = 'JSON-LD',
  className = 'card overflow-hidden mb-10',
}: {
  url: string;
  // The copy already embedded in the page, when there is one, so opening the
  // panel needs no second request.
  document?: unknown;
  label?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data: fetched, error, isLoading } = useSWR<unknown>(
    open && document == null ? url : null,
    ldFetcher
  );
  const data = document ?? fetched;
  const text = data ? JSON.stringify(data, null, 2) : '';

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access is denied outside a secure context; the text is
      // selectable either way, so there is nothing to recover from.
    }
  };

  return (
    <div className={className}>
      <div className="flex items-center gap-2 px-4 py-2.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex items-center gap-2 text-sm text-foreground font-medium hover:text-primary transition-colors"
        >
          {open ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          {label}
        </button>
        <span className="text-xs text-muted-foreground">
          this record as linked data
        </span>
        {open && data != null && (
          <button
            type="button"
            onClick={copy}
            className="ml-auto flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border border-border text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                Copied
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                Copy
              </>
            )}
          </button>
        )}
      </div>

      {open && (
        <div className="border-t border-border">
          {isLoading && (
            <p className="px-4 py-3 text-xs text-muted-foreground">Loading…</p>
          )}
          {error && (
            <p className="px-4 py-3 text-xs text-destructive">
              Could not load the JSON-LD for this record.
            </p>
          )}
          {data != null && (
            <pre className="px-4 py-3 text-xs font-mono text-foreground overflow-auto max-h-96 whitespace-pre">
              {text}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
