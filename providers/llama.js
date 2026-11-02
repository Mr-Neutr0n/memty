import { chatOpenAICompatible } from './openai-compatible.js';
import { getModel } from './registry.js';

const base = (process.env.OPEN_ROUTER_API_URL || 'https://openrouter.ai/api/v1/chat/completions').replace(/\/+$/, '');
const apiUrl = base.endsWith('/chat/completions') ? base : `${base}/chat/completions`;

export function chat(options) {
    return chatOpenAICompatible({ ...options, apiKey: process.env.OPEN_ROUTER_API_KEY, apiUrl, model: getModel('llama').model, extraHeaders: { 'HTTP-Referer': process.env.OPEN_ROUTER_SITE_URL || 'http://localhost:3001', 'X-Title': process.env.OPEN_ROUTER_APP_NAME || 'Memty' } });
}
