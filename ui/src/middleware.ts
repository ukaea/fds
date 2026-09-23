import { NextRequest, NextResponse } from 'next/server';

// The identifier paths FDS publishes. A browser asking for HTML gets the landing
// page; anything asking for JSON-LD is handed to the route below, which answers
// from FDS with the media type intact.
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

export function middleware(request: NextRequest) {
  if (!(request.headers.get('accept') ?? '').includes('application/ld+json')) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = `/api/identifiers${request.nextUrl.pathname}`;
  return NextResponse.rewrite(url);
}
