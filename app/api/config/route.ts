import { NextResponse } from 'next/server';
import { MODEL_REGISTRY, getModelRates, isConfigured } from '../../../providers/registry.js';

export function GET() {
  return NextResponse.json({
    googleClientId: process.env.GOOGLE_CLIENT_ID || null,
    models: MODEL_REGISTRY.map(model => ({ id: model.id, displayName: model.displayName, provider: model.provider, contextWindow: model.contextWindow, costTier: model.costTier, rates: getModelRates(model.id), speedTier: model.speedTier, vision: model.vision, code: model.code, available: isConfigured(model) }))
  }, { headers: { 'Cache-Control': 'no-store' } });
}
