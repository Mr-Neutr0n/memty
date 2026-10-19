import { chatOpenAICompatible } from './openai-compatible.js';
import { getModel } from './registry.js';

export function chat(options) {
    return chatOpenAICompatible({ ...options, apiKey: process.env.KIMI_API_KEY, apiUrl: process.env.KIMI_API_URL || 'https://api.moonshot.ai/v1/chat/completions', model: getModel('kimi').model });
}
