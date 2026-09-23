import { NextResponse } from 'next/server';

// Never prerendered: the whole point is to answer from the environment the
// container is running in, not the one that built it.
export const dynamic = 'force-dynamic';

export async function GET() {
  const issuer = process.env.AUTH_KEYCLOAK_ISSUER;

  return NextResponse.json({
    logoutEndpoint: issuer ? `${issuer}/protocol/openid-connect/logout` : null,
  });
}
