import { NextResponse } from 'next/server';

// Never prerendered: the version is that of the FDS this container talks to,
// which can change without the UI being rebuilt.
export const dynamic = 'force-dynamic';

// FDS reports its version on /health, which is outside the /v1 routes that the
// /api/v1 proxy forwards.
export async function GET() {
  const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

  try {
    const upstream = await fetch(`${backend}/health`, { cache: 'no-store' });
    if (!upstream.ok) {
      return NextResponse.json({ version: null }, { status: 502 });
    }
    const { version } = await upstream.json();
    return NextResponse.json({ version: version ?? null });
  } catch (error) {
    console.error('[Version] Error:', error);
    return NextResponse.json({ version: null }, { status: 502 });
  }
}
