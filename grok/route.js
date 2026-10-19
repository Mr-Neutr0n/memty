import dotenv from 'dotenv';
import { getConversation, saveConversation, clearConversation } from '../providers/conversation.js';

dotenv.config();

const API_URL = 'https://api.x.ai/v1/chat/completions';
const MODEL = process.env.GROK_MODEL || 'grok-3-mini';

export async function generateGrokResponse(userId, message) {
    if (!process.env.GROK_API_KEY) throw new Error('Grok is not configured. Set GROK_API_KEY and restart the server.');
    const history = getConversation(userId, 'grok');
    const response = await fetch(API_URL, {
        method: 'POST',
        headers: { Authorization: `Bearer ${process.env.GROK_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: MODEL, messages: [...history, { role: 'user', content: message }] })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`Grok request failed: ${payload?.error?.message || `HTTP ${response.status}`}`);
    const text = payload?.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error('Grok returned an empty response.');
    saveConversation(userId, 'grok', [...history, { role: 'user', content: message }, { role: 'assistant', content: text }]);
    return text;
}

export function clearGrokConversation(userId) { clearConversation(userId, 'grok'); }
