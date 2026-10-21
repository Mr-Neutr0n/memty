import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 35;

type RouteContext = { params: Promise<{ path: string[] }> };
const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

async function proxy(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const target = (process.env.PROXY_TARGET || 'http://localhost:3002').replace(/\/$/, '');
  const incomingUrl = new URL(request.url);
  const upstreamUrl = `${target}/users/${path.map(encodeURIComponent).join('/')}${incomingUrl.search}`;
  const isGoogleSignIn = request.method === 'POST' && path.length === 1 && path[0] === 'google';
  const headers = new Headers();
  for (const name of ['accept', 'content-type', 'cookie', 'authorization', 'user-agent', 'origin']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer(),
      cache: 'no-store',
      signal: AbortSignal.timeout(isGoogleSignIn ? 30_000 : 10_000),
      redirect: 'manual',
    });
    const responseHeaders = new Headers();
    for (const name of ['content-type', 'cache-control', 'set-cookie', 'location']) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    const timedOut = error instanceof Error && (
      error.name === 'TimeoutError' || error.name === 'AbortError' ||
      (error.cause instanceof Error && (error.cause.name === 'TimeoutError' || error.cause.name === 'AbortError'))
    );
    const offline = error instanceof TypeError;
    return NextResponse.json({
      error: timedOut ? 'Google sign-in timed out.' : offline ? 'Authentication backend is offline.' : 'Proxy error',
      message: timedOut
        ? 'Google verification or account lookup took too long. Please retry; if it continues, check backend connectivity to Google and MongoDB.'
        : error instanceof Error ? error.message : 'Unable to contact authentication backend.',
    }, { status: timedOut ? 504 : offline ? 503 : 500 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
