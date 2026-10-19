import { chat } from './providers/index.js';

export async function generateResponse(_userId, message, modelId = 'gemini-flash', context = {}) {
    const messages = Array.isArray(context.messages) ? context.messages : [];
    const normalized = messages
        .filter(item => item && (item.role === 'user' || item.role === 'assistant') && typeof item.content === 'string')
        .slice(-48)
        .map(item => ({ role: item.role, content: item.content.slice(0, 30000) }));
    normalized.push({ role: 'user', content: message });
    const memory = [
        context.workingSummary ? `Current conversation summary:\n${context.workingSummary}` : '',
        context.memoryBrief || ''
    ].filter(Boolean).join('\n\n');
    return chat({ messages: normalized, memory, modelId, auto: modelId === 'auto', allowFallback: context.allowFallback !== false });
}

export function clearConversationHistory() {
    // Conversation history is now owned by the authenticated MongoDB memory service.
}
