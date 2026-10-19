import dotenv from 'dotenv';
import { getConversation, saveConversation, clearConversation } from '../providers/conversation.js';

dotenv.config();

const API_URL = (process.env.OPEN_ROUTER_API_URL || 'https://openrouter.ai/api/v1/chat/completions').replace(/\/+$/, '');
const MODEL = process.env.LLAMA_MODEL || 'meta-llama/llama-3.3-70b-instruct:free';

export async function generateLlamaResponse(userId, message) {
    if (!process.env.OPEN_ROUTER_API_KEY) throw new Error('Meta Llama is not configured. Set OPEN_ROUTER_API_KEY and restart the server.');
    const history = getConversation(userId, 'llama');
    const response = await fetch(`${API_URL}/chat/completions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${process.env.OPEN_ROUTER_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: MODEL, messages: [...history, { role: 'user', content: message }] })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`Meta Llama request failed: ${payload?.error?.message || `HTTP ${response.status}`}`);
    const text = payload?.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error('Meta Llama returned an empty response.');
    saveConversation(userId, 'llama', [...history, { role: 'user', content: message }, { role: 'assistant', content: text }]);
    return text;
}

export function clearLlamaConversation(userId) { clearConversation(userId, 'llama'); }
