export async function chat({ messages, memory = '', stream = false, modelId = 'claude-haiku' }) {
    if (stream) throw new Error('Streaming is not available yet.');
    const apiKey = process.env.CLAUDE_API_KEY;
    if (!apiKey) throw new Error('Claude is not configured.');
    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST', headers: { 'x-api-key': apiKey, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
        body: JSON.stringify({ model: process.env.CLAUDE_MODEL || 'claude-haiku-4-5-20251001', max_tokens: Number(process.env.CLAUDE_MAX_OUTPUT_TOKENS || 2048), system: `${BASE_PROMPT}${memory ? `\n\n${memory}` : ''}`, messages: toClaudeMessages(messages) }),
        signal: AbortSignal.timeout(Number(process.env.CLAUDE_TIMEOUT_MS || 30000))
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.error?.message || `Claude returned HTTP ${response.status}`);
    const text = (payload.content || []).filter(part => part.type === 'text').map(part => part.text).join('');
    if (!text.trim()) throw new Error('Claude returned an empty response.');
    return { text, model: modelId, usage: payload.usage || null };
}

function toClaudeMessages(messages) { return messages.map(message => ({ role: message.role === 'assistant' ? 'assistant' : 'user', content: message.content })); }
const BASE_PROMPT = 'You are a helpful, accurate AI assistant. Be clear and practical. The user may switch models; treat the supplied neutral chat history as the shared conversation.';
