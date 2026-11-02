import dotenv from 'dotenv';
import { getConversation, saveConversation, clearConversation } from '../providers/conversation.js';

dotenv.config();

const configuredApiUrl = (
    process.env.OPEN_ROUTER_API_URL ||
    'https://openrouter.ai/api/v1/chat/completions'
).replace(/\/+$/, '');
const API_URL = configuredApiUrl.endsWith('/chat/completions')
    ? configuredApiUrl
    : `${configuredApiUrl}/chat/completions`;
const MODEL = process.env.OPEN_ROUTER_MODEL_ID || 'nvidia/nemotron-3.5-lightning:free';
const SYSTEM_PROMPT = 'You are a helpful, clear, and concise AI assistant.';

export async function generateNvidiaResponse(userId, message) {
    if (!process.env.OPEN_ROUTER_API_KEY) {
        throw new Error('NVIDIA is not configured. Set OPEN_ROUTER_API_KEY and restart the server.');
    }
    const history = getConversation(userId, 'nvidia');
    const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${process.env.OPEN_ROUTER_API_KEY}`,
            'Content-Type': 'application/json',
            'HTTP-Referer': process.env.OPEN_ROUTER_SITE_URL || 'http://localhost:3001',
            'X-Title': process.env.OPEN_ROUTER_APP_NAME || 'Memty'
        },
        body: JSON.stringify({
            model: MODEL,
            messages: [{ role: 'system', content: SYSTEM_PROMPT }, ...history, { role: 'user', content: message }],
            temperature: 0.7,
            max_tokens: Number.parseInt(process.env.OPEN_ROUTER_MAX_OUTPUT_TOKENS || '1024', 10)
        })
    });
    return saveOpenRouterResponse(response, userId, message, history);
}

async function saveOpenRouterResponse(response, userId, message, history) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`NVIDIA request failed: ${payload?.error?.message || `HTTP ${response.status}`}`);
    const text = payload?.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error('NVIDIA returned an empty response.');
    saveConversation(userId, 'nvidia', [...history, { role: 'user', content: message }, { role: 'assistant', content: text }]);
    return text;
}

export function clearNvidiaConversation(userId) {
    clearConversation(userId, 'nvidia');
}
