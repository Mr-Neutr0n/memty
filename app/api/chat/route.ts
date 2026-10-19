import { NextResponse } from 'next/server';
import { generateResponse } from '../../../gemini-service.js';
import { getModel } from '../../../providers/registry.js';

export const runtime = 'nodejs';
export const maxDuration = 60;

const requestWindowMs = 60_000;
const requestLimit = 30;
const requests = new Map<string, { count: number; resetAt: number }>();

function rateLimited(key: string) {
  const now = Date.now();
  const bucket = requests.get(key);
  if (bucket && bucket.resetAt <= now) requests.delete(key);
  if (!requests.has(key)) {
    if (requests.size >= 10_000) {
      for (const [address, entry] of requests) if (entry.resetAt <= now) requests.delete(address);
      if (requests.size >= 10_000) return true;
    }
    requests.set(key, { count: 1, resetAt: now + requestWindowMs });
    return false;
  }
  const current = requests.get(key)!;
  current.count += 1;
  return current.count > requestLimit;
}

async function backendRequest(request: Request, path: string, body?: unknown) {
  const target = (process.env.PROXY_TARGET || 'http://localhost:3002').replace(/\/$/, '');
  return fetch(`${target}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      cookie: request.headers.get('cookie') || '',
      ...(body === undefined ? {} : { 'content-type': 'application/json' })
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
    signal: AbortSignal.timeout(path.endsWith('/commit') ? 50_000 : path.endsWith('/context') ? 20_000 : 12_000)
  });
}

async function parseBackend(response: Response) {
  const data = await response.json().catch(() => ({}));
  return { data, ok: response.ok, status: response.status };
}

async function readBody(request: Request, maxBytes: number) {
  if (!request.body) return '';
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let body = '';
  let bytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    bytes += value.byteLength;
    if (bytes > maxBytes) { await reader.cancel(); throw new RangeError('body too large'); }
    body += decoder.decode(value, { stream: true });
  }
  return body + decoder.decode();
}

export async function POST(request: Request) {
  const clientKey = request.headers.get('x-real-ip')?.slice(0, 80) || 'unknown';
  if (rateLimited(clientKey)) return NextResponse.json({ error: 'Too many requests. Try again in a minute.' }, { status: 429, headers: { 'Retry-After': '60', 'Cache-Control': 'no-store' } });
  try {
    const length = Number(request.headers.get('content-length') || 0);
    if (length > 100 * 1024) return NextResponse.json({ error: 'Request body is too large.' }, { status: 413 });
    let body: unknown;
    try { body = JSON.parse(await readBody(request, 100 * 1024)); } catch (error) {
      return NextResponse.json({ error: error instanceof RangeError ? 'Request body is too large.' : 'Request body must be valid JSON.' }, { status: error instanceof RangeError ? 413 : 400 });
    }
    if (!body || typeof body !== 'object') return NextResponse.json({ error: 'Message is required.' }, { status: 400 });
    const { message, model, conversationId, compareWith } = body as { message?: unknown; model?: unknown; conversationId?: unknown; compareWith?: unknown };
    if (typeof message !== 'string' || !message.trim() || message.length > 30_000) return NextResponse.json({ error: 'A message of 1–30,000 characters is required.' }, { status: 400 });
    const selectedModel = typeof model === 'string' ? model : 'gemini-flash';
    if (selectedModel !== 'auto' && !getModel(selectedModel)) return NextResponse.json({ error: 'Selected model is not available.' }, { status: 400 });
    const activeConversationId = typeof conversationId === 'string' && /^[\w-]{8,80}$/.test(conversationId) ? conversationId : crypto.randomUUID();

    let authResponse: Response;
    try { authResponse = await backendRequest(request, '/users/me'); }
    catch { return NextResponse.json({ error: 'Authentication service is unavailable. Start the backend and sign in again.' }, { status: 503 }); }
    if (authResponse.status === 401) return NextResponse.json({ error: 'Your session has expired. Sign in again.' }, { status: 401 });
    if (!authResponse.ok) return NextResponse.json({ error: 'Could not verify your account.' }, { status: 503 });
    const auth = await parseBackend(authResponse);
    const userId = auth.data?.data?.user?._id;
    if (typeof userId !== 'string') return NextResponse.json({ error: 'Could not verify your account.' }, { status: 401 });

    const contextWindow = selectedModel === 'auto' ? 128000 : getModel(selectedModel)?.contextWindow || 128000;
    const contextResponse = await backendRequest(request, '/memory/context', { conversationId: activeConversationId, query: message.trim().slice(0, 4000), contextWindow });
    const contextResult = await parseBackend(contextResponse);
    if (!contextResponse.ok) return NextResponse.json({ error: contextResult.data?.message || 'Memory service is unavailable.' }, { status: contextResponse.status });
    const context = contextResult.data.data || {};
    const result = await generateResponse(userId, message.trim(), selectedModel, context);

    let comparison: { model: string; reply: string; usage?: { inputTokens: number; outputTokens: number; estimatedCostUsd: number | null } } | null = null;
    if (typeof compareWith === 'string' && compareWith !== selectedModel && compareWith !== 'auto') {
      try {
        const second = await generateResponse(userId, message.trim(), compareWith, { ...context, allowFallback: false });
        comparison = { model: second.model, reply: second.text, usage: second.usage };
      } catch (error) {
        comparison = { model: compareWith, reply: error instanceof Error ? `Comparison unavailable: ${error.message}` : 'Comparison unavailable.' };
      }
    }

    const commitResponse = await backendRequest(request, '/memory/commit', {
      conversationId: activeConversationId, message: message.trim(), response: result.text, model: result.model,
      usage: result.usage, memoryUsed: context.usedMemories || [],
      ...(comparison?.usage ? { comparisonUsage: { model: comparison.model, ...comparison.usage } } : {})
    });
    if (!commitResponse.ok) console.error('Memory commit failed:', commitResponse.status);
    return NextResponse.json({ reply: result.text, model: result.model, fallback: result.fallback, requestedModel: result.requestedModel, memoryUsed: context.usedMemories || [], conversationId: activeConversationId, comparison, usage: result.usage }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    console.error('Chat API error:', error);
    return NextResponse.json({ error: 'AI request failed. Try another model or try again shortly.' }, { status: 502, headers: { 'Cache-Control': 'no-store' } });
  }
}
