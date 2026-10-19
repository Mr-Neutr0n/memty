import dotenv from 'dotenv';
import { getConversation, saveConversation, clearConversation } from '../providers/conversation.js';

dotenv.config();

const API_URL = 'https://api.moonshot.ai/v1/chat/completions';
const MODEL = process.env.KIMI_MODEL || 'kimi-k2-turbo-preview';

export async function generateKimiResponse(userId, message) {
    if (!process.env.KIMI_API_KEY) throw new Error('Kimi is not configured. Set KIMI_API_KEY and restart the server.');
    const history = getConversation(userId, 'kimi');
    const response = await fetch(API_URL, {
        method: 'POST',
        headers: { Authorization: `Bearer ${process.env.KIMI_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: MODEL, messages: [...history, { role: 'user', content: message }] })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`Kimi request failed: ${payload?.error?.message || `HTTP ${response.status}`}`);
    const text = payload?.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error('Kimi returned an empty response.');
    saveConversation(userId, 'kimi', [...history, { role: 'user', content: message }, { role: 'assistant', content: text }]);
    return text;
}

export function clearKimiConversation(userId) { clearConversation(userId, 'kimi'); }
