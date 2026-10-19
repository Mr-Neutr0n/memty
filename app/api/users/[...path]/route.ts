import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type RouteContext = { params: Promise<{ path: string[] }> };
const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const target = (process.env.PROXY_TARGET || 'http://localhost:3002').replace(/\/$/, '');
  const incomingUrl = new URL(request.url);
  const upstreamUrl = `${target}/users/${path.map(encodeURIComponent).join('/')}${incomingUrl.search}`;
  const headers = new Headers();
  for (const name of ['accept', 'content-type', 'cookie', 'authorization', 'user-agent']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer(),
      cache: 'no-store',
      signal: AbortSignal.timeout(10_000),
      redirect: 'manual',
    });
    const responseHeaders = new Headers();
    for (const name of ['content-type', 'cache-control', 'set-cookie', 'location']) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    const offline = error instanceof TypeError || (error instanceof Error && error.name === 'TimeoutError');
    return NextResponse.json({
      error: offline ? 'Authentication backend is offline.' : 'Proxy error',
      message: error instanceof Error ? error.message : 'Unable to contact authentication backend.',
    }, { status: offline ? 503 : 500 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
