import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const readinessTimeoutMs = 1_000;

async function backendReadiness(): Promise<'ok' | 'degraded' | 'unavailable'> {
  const target = (process.env.PROXY_TARGET || 'http://localhost:3002').replace(/\/$/, '');
  try {
    const response = await fetch(`${target}/health`, {
      cache: 'no-store',
      headers: { accept: 'application/json' },
      redirect: 'manual',
      signal: AbortSignal.timeout(readinessTimeoutMs),
    });
    const body: unknown = await response.json().catch(() => null);
    const reported = body && typeof body === 'object' && 'status' in body
      ? (body as { status: unknown }).status
      : undefined;
    if (response.ok && reported === 'ok') return 'ok';
    if (reported === 'degraded') return 'degraded';
    return 'unavailable';
  } catch {
    return 'unavailable';
  }
}

export async function GET() {
  const readiness = await backendReadiness();
  return NextResponse.json({
    liveness: 'ok',
    readiness,
    timestamp: new Date().toISOString(),
  }, {
    status: readiness === 'ok' ? 200 : 503,
    headers: { 'Cache-Control': 'no-store' },
  });
}
