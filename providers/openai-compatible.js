const BASE_PROMPT = 'You are a helpful, accurate AI assistant. Be clear and practical. The user may switch models; treat the supplied neutral chat history as the shared conversation.';

export async function chatOpenAICompatible({ apiKey, apiUrl, model, messages, memory = '', modelId, stream = false, extraHeaders = {}, maxTokens = 2048 }) {
    if (stream) throw new Error('Streaming is not available yet.');
    if (!apiKey) throw new Error(`${modelId} is not configured.`);
    const response = await fetch(apiUrl, {
        method: 'POST',
        headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json', ...extraHeaders },
        body: JSON.stringify({ model, messages: [{ role: 'system', content: `${BASE_PROMPT}${memory ? `\n\n${memory}` : ''}` }, ...messages], max_tokens: maxTokens }),
        signal: AbortSignal.timeout(Number(process.env.PROVIDER_TIMEOUT_MS || 30000))
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.error?.message || `${modelId} returned HTTP ${response.status}`);
    const text = payload?.choices?.[0]?.message?.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error(`${modelId} returned an empty response.`);
    return { text, model: modelId, usage: payload.usage || null };
}
