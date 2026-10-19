import dotenv from 'dotenv';
import { getConversation, saveConversation, clearConversation } from '../providers/conversation.js';

dotenv.config();

const API_URL = (process.env.OPEN_ROUTER_API_URL || 'https://openrouter.ai/api/v1/chat/completions').replace(/\/+$/, '');
const MODEL = process.env.OPEN_ROUTER_OPEN_AI_MODEL_ID || process.env.OPEN_ROUTER_OPENAI_MODEL_ID || 'openai/gpt-4o-mini';

export async function generateChatGptResponse(userId, message) {
    const apiKey = process.env.OPEN_ROUTER_OPEN_API_KEYS || process.env.OPEN_ROUTER_OPENAI_API_KEY;
    if (!apiKey) throw new Error('ChatGPT is not configured. Set OPEN_ROUTER_OPEN_API_KEY and restart the server.');
    const history = getConversation(userId, 'chatgpt');
    const response = await fetch(`${API_URL}/chat/completions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: MODEL,
            messages: [...history, { role: 'user', content: message }],
            max_tokens: Number.parseInt(process.env.OPEN_ROUTER_OPEN_AI_MAX_OUTPUT_TOKENS || '1024', 10)
        })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`ChatGPT request failed: ${payload?.error?.message || `HTTP ${response.status}`}`);
    const text = payload?.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error('ChatGPT returned an empty response.');
    saveConversation(userId, 'chatgpt', [...history, { role: 'user', content: message }, { role: 'assistant', content: text }]);
    return text;
}

export function clearChatGptConversation(userId) {
    clearConversation(userId, 'chatgpt');
}
