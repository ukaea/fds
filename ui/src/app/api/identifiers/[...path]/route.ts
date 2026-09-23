import { NextRequest, NextResponse } from 'next/server';

import { auth } from '@/auth';

const LD_JSON = 'application/ld+json';

// Unlike the /api/v1 proxy this does not re-encode the body, because re-encoding
// would answer application/json to a caller that asked for JSON-LD.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

  const headers = new Headers({ Accept: LD_JSON });
  const offered = request.headers.get('authorization');
  if (offered) {
    headers.set('Authorization', offered);
  } else {
    const session = await auth();
    if (session?.accessToken) headers.set('Authorization', `Bearer ${session.accessToken}`);
  }

  try {
    const upstream = await fetch(`${backend}/${path.join('/')}`, { headers, cache: 'no-store' });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { 'content-type': upstream.headers.get('content-type') ?? LD_JSON },
    });
  } catch (error) {
    console.error('[Identifiers] Error:', error);
    return NextResponse.json({ error: 'Failed to resolve identifier' }, { status: 502 });
  }
}
