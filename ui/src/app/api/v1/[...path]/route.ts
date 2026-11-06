import { NextRequest, NextResponse } from 'next/server';

import { auth } from '@/auth';
import { API_BASE, API_VERSION } from '@/lib/api-version';

// This API route acts as a proxy to the backend FastAPI server
// It handles all /api/v1/* requests and forwards them to the backend
export async function GET(request: NextRequest) {
  return proxyRequest(request);
}

export async function POST(request: NextRequest) {
  return proxyRequest(request);
}

export async function PUT(request: NextRequest) {
  return proxyRequest(request);
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request);
}

export async function PATCH(request: NextRequest) {
  return proxyRequest(request);
}

async function proxyRequest(request: NextRequest) {
  const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

  // This route's own path is under API_BASE; FDS serves the same path under
  // API_VERSION.
  const path = request.nextUrl.pathname.replace(API_BASE, API_VERSION);
  const search = request.nextUrl.search;

  const targetUrl = `${backendUrl}${path}${search}`;

  console.log(`[API Proxy] ${request.method} ${request.nextUrl.pathname} -> ${targetUrl}`);

  try {
    const session = await auth();
    // Only forward necessary headers (avoid Next.js internal headers)
    const headers = new Headers();
    const contentType = request.headers.get('content-type');
    if (contentType) {
      headers.set('content-type', contentType);
    }
    // FDS negotiates on Accept: without it every request reads as plain JSON
    // and the JSON-LD representations are unreachable through the UI.
    const accept = request.headers.get('accept');
    if (accept) {
      headers.set('accept', accept);
    }

    // Inject Authorization header if user is authenticated
    if (session?.accessToken) {
      headers.set('Authorization', `Bearer ${session.accessToken}`);
    }

    // Forward the request to the backend
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: request.method !== 'GET' && request.method !== 'HEAD'
        ? await request.text()
        : undefined,
      redirect: 'follow',
    });

    // Get the response body as text first
    const responseText = await response.text();

    // Try to parse as JSON, fall back to text
    let responseData;
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = responseText;
    }

    // FDS answers some routes in JSON or JSON-LD by the Accept header. Keep the
    // JSON-LD media type it chose, and its Vary, so that a cache keeps the two
    // answers apart.
    const answerHeaders = new Headers();
    const vary = response.headers.get('vary');
    if (vary) {
      answerHeaders.set('vary', vary);
    }
    if (response.headers.get('content-type')?.startsWith('application/ld+json')) {
      answerHeaders.set('content-type', 'application/ld+json');
    }

    return NextResponse.json(responseData, {
      status: response.status,
      headers: answerHeaders,
    });
  } catch (error) {
    console.error(`[API Proxy] Error:`, error);
    return NextResponse.json(
      { error: 'Failed to proxy request', details: String(error) },
      { status: 500 }
    );
  }
}
