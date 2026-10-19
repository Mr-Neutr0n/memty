import { chatOpenAICompatible } from './openai-compatible.js';
import { getModel } from './registry.js';

export function chat(options) {
    return chatOpenAICompatible({ ...options, apiKey: process.env.GROK_API_KEY, apiUrl: 'https://api.x.ai/v1/chat/completions', model: getModel('grok-ai').model });
}
