export const MODEL_REGISTRY = [
    { id: 'gemini-flash', displayName: 'Gemini Flash', provider: 'Google', model: process.env.GEMINI_MODEL || 'gemini-2.5-flash', contextWindow: 1000000, costTier: 'low', speedTier: 'fast', vision: false, code: true, keyEnv: 'GEMINI_API_KEY', fallback: ['claude-haiku', 'nemotron'] },
    { id: 'claude-haiku', displayName: 'Claude Haiku', provider: 'Anthropic', model: process.env.CLAUDE_MODEL || 'claude-haiku-4-5-20251001', contextWindow: 200000, costTier: 'low', speedTier: 'fast', vision: false, code: true, keyEnv: 'CLAUDE_API_KEY', fallback: ['gemini-flash', 'chatgpt'] },
    { id: 'chatgpt', displayName: 'ChatGPT', provider: 'OpenAI via OpenRouter', model: process.env.OPEN_ROUTER_OPEN_AI_MODEL_ID || 'openai/gpt-4o-mini', contextWindow: 128000, costTier: 'medium', speedTier: 'fast', vision: false, code: true, keyEnv: 'OPEN_ROUTER_OPEN_API_KEYS', fallback: ['gemini-flash', 'nemotron'] },
    { id: 'grok-ai', displayName: 'Grok AI', provider: 'xAI', model: process.env.GROK_MODEL || 'grok-3-mini', contextWindow: 131072, costTier: 'medium', speedTier: 'fast', vision: false, code: true, keyEnv: 'GROK_API_KEY', fallback: ['gemini-flash', 'chatgpt'] },
    { id: 'kimi', displayName: 'Moonshot AI Kimi', provider: 'Moonshot AI', model: process.env.KIMI_MODEL || 'kimi-k2-turbo-preview', contextWindow: 128000, costTier: 'medium', speedTier: 'medium', vision: false, code: true, keyEnv: 'KIMI_API_KEY', fallback: ['gemini-flash', 'chatgpt'] },
    { id: 'nemotron', displayName: 'NVIDIA Nemotron', provider: 'NVIDIA via OpenRouter', model: process.env.OPEN_ROUTER_MODEL_ID || 'nvidia/nemotron-3.5-lightning:free', contextWindow: 131072, costTier: 'low', speedTier: 'fast', vision: false, code: true, keyEnv: 'OPEN_ROUTER_API_KEY', fallback: ['gemini-flash', 'chatgpt'] },
    { id: 'llama', displayName: 'Meta Llama', provider: 'Meta via OpenRouter', model: process.env.LLAMA_MODEL || 'meta-llama/llama-3.3-70b-instruct:free', contextWindow: 131072, costTier: 'low', speedTier: 'medium', vision: false, code: true, keyEnv: 'OPEN_ROUTER_API_KEY', fallback: ['gemini-flash', 'nemotron'] },
];

export function getModel(id) { return MODEL_REGISTRY.find(model => model.id === id); }
export function isConfigured(model) { return Boolean(model && process.env[model.keyEnv]); }

export function getModelRates(modelId) {
    const prefix = `NEXOR_${modelId.toUpperCase().replace(/-/g, '_')}`;
    const inputValue = process.env[`${prefix}_INPUT_USD_PER_MILLION`];
    const outputValue = process.env[`${prefix}_OUTPUT_USD_PER_MILLION`];
    if (!inputValue?.trim() || !outputValue?.trim()) return null;
    const inputUsdPerMillion = Number(inputValue);
    const outputUsdPerMillion = Number(outputValue);
    return Number.isFinite(inputUsdPerMillion) && inputUsdPerMillion >= 0 && Number.isFinite(outputUsdPerMillion) && outputUsdPerMillion >= 0 ? { inputUsdPerMillion, outputUsdPerMillion } : null;
}
