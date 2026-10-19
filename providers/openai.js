import { chatOpenAICompatible } from './openai-compatible.js';
import { getModel } from './registry.js';

const base = (process.env.OPEN_ROUTER_API_URL || 'https://openrouter.ai/api/v1/chat/completions').replace(/\/+$/, '');
const apiUrl = base.endsWith('/chat/completions') ? base : `${base}/chat/completions`;

export function chat(options) {
    return chatOpenAICompatible({ ...options, apiKey: process.env.OPEN_ROUTER_OPEN_API_KEYS || process.env.OPEN_ROUTER_OPENAI_API_KEY, apiUrl, model: getModel('chatgpt').model });
}
