import { NextRequest, NextResponse } from 'next/server';

import { prefers } from '@/lib/negotiation';

// The identifier paths FDS publishes. A browser asking for HTML gets the landing
// page; anything that prefers JSON-LD to HTML is handed to the route below,
// which answers from FDS with the media type intact.
export const config = {
  matcher: [
    '/datasets/:id',
    '/collections/:id',
    '/sources/:id',
    '/activities/:id',
    '/devices/:name',
    '/devices/:name/shots/:shot',
  ],
};

// The page and the JSON-LD share an address, but no Vary is set here: Next
// replaces a page's Vary with its own, and sends pages as no-store, so no cache
// keeps one to answer a request for JSON-LD. The JSON-LD route sends Vary: Accept,
// so no cache answers a browser with it either.
export function proxy(request: NextRequest) {
  if (!prefers(request.headers.get('accept'), 'application/ld+json', 'text/html')) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = `/api/identifiers${request.nextUrl.pathname}`;
  return NextResponse.rewrite(url);
}
