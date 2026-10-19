import dotenv from 'dotenv';

dotenv.config();

const CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages';
const CLAUDE_MODEL = 'claude-haiku-4-5-20251001';
const CLAUDE_MAX_OUTPUT_TOKENS = Number.parseInt(
    process.env.CLAUDE_MAX_OUTPUT_TOKENS || '2048',
    10
);
const CLAUDE_TIMEOUT_MS = Number.parseInt(
    process.env.CLAUDE_TIMEOUT_MS || '30000',
    10
);
const MAX_HISTORY_MESSAGES = 40;

const SYSTEM_PROMPT = `You are a helpful AI assistant created by Rohan, a student at MS Ramaiah Institute of Technology.
You are talking to a user through a chat interface. Be friendly, helpful, clear, and concise. Preserve useful context across turns.`;

const conversationHistory = new Map();

const getHistoryKey = userId => `${userId}:claude`;

function getConfiguredPositiveInteger(value, fallback) {
    return Number.isInteger(value) && value > 0 ? value : fallback;
}

export async function generateClaudeResponse(userId, message) {
    const apiKey = process.env.CLAUDE_API_KEY;
    if (!apiKey) {
        throw new Error('Claude is not configured. Set CLAUDE_API_KEY and restart the server.');
    }

    const historyKey = getHistoryKey(userId);
    const history = conversationHistory.get(historyKey) || [];
    const abortController = new AbortController();
    const timeoutMs = getConfiguredPositiveInteger(CLAUDE_TIMEOUT_MS, 30000);
    const maxOutputTokens = getConfiguredPositiveInteger(CLAUDE_MAX_OUTPUT_TOKENS, 2048);
    const timeout = setTimeout(() => abortController.abort(), timeoutMs);

    let response;
    try {
        response = await fetch(CLAUDE_API_URL, {
            method: 'POST',
            headers: {
                'x-api-key': apiKey,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            },
            body: JSON.stringify({
                model: CLAUDE_MODEL,
                max_tokens: maxOutputTokens,
                system: SYSTEM_PROMPT,
                messages: [
                    ...history,
                    { role: 'user', content: message }
                ]
            }),
            signal: abortController.signal
        });
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error(`Claude request timed out after ${timeoutMs / 1000} seconds.`);
        }
        throw new Error(`Claude request failed: ${error.message}`);
    } finally {
        clearTimeout(timeout);
    }

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        const providerMessage = payload?.error?.message || `HTTP ${response.status}`;
        throw new Error(`Claude request failed: ${providerMessage}`);
    }

    const text = Array.isArray(payload?.content)
        ? payload.content
            .filter(part => part?.type === 'text' && typeof part.text === 'string')
            .map(part => part.text)
            .join('')
        : '';
    if (!text.trim()) {
        throw new Error('Claude returned an empty response.');
    }

    conversationHistory.set(historyKey, [
        ...history,
        { role: 'user', content: message },
        { role: 'assistant', content: text }
    ].slice(-MAX_HISTORY_MESSAGES));
    return text;
}

export function clearClaudeConversationHistory(userId) {
    conversationHistory.delete(getHistoryKey(userId));
}
