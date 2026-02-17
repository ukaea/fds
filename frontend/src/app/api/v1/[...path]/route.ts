import { NextRequest, NextResponse } from 'next/server';

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
  const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000/api';

  // Extract the path after /api/v1/
  const path = request.nextUrl.pathname.replace('/api/v1', '/v1');
  const search = request.nextUrl.search;

  const targetUrl = `${backendUrl}${path}${search}`;

  console.log(`[API Proxy] ${request.method} ${request.nextUrl.pathname} -> ${targetUrl}`);

  try {
    // Only forward necessary headers (avoid Next.js internal headers)
    const headers = new Headers();
    const contentType = request.headers.get('content-type');
    if (contentType) {
      headers.set('content-type', contentType);
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

    // Return JSON response
    return NextResponse.json(responseData, {
      status: response.status,
    });
  } catch (error) {
    console.error(`[API Proxy] Error:`, error);
    return NextResponse.json(
      { error: 'Failed to proxy request', details: String(error) },
      { status: 500 }
    );
  }
}
