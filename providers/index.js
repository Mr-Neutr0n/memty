import { chat as geminiChat } from './gemini.js';
import { chat as claudeChat } from './claude.js';
import { chat as grokChat } from './grok.js';
import { chat as kimiChat } from './kimi.js';
import { chat as openaiChat } from './openai.js';
import { chat as nvidiaChat } from './nvidia.js';
import { chat as llamaChat } from './llama.js';
import { getModel, getModelRates, isConfigured } from './registry.js';

const adapters = {
    'gemini-flash': options => geminiChat(options),
    'claude-haiku': options => claudeChat(options),
    'grok-ai': options => grokChat(options),
    kimi: options => kimiChat(options),
    chatgpt: options => openaiChat(options),
    nemotron: options => nvidiaChat(options),
    llama: options => llamaChat(options)
};

function selectAutoModel(message, memory = '') {
    const text = String(message || '');
    const context = String(memory || '');
    const deepReasoning = /\b(prove|formal proof|multi[- ]hop|step[- ]by[- ]step|architect|distributed system|security audit|trade[- ]offs|derive)\b/i.test(text);
    const longDocument = text.length > 7000 || /long document|analyze this document|entire document/i.test(text);
    const codeTask = /```|\b(code|typescript|javascript|python|debug|stack trace|compile|function|class|refactor|bug)\b/i.test(text);
    const structuredTask = /\b(json|schema|extract|classify|format as|return only)\b/i.test(text);
    const memoryRelevant = context.length > 120 && /\b(remember|previous|above|my project|my preference|as discussed)\b/i.test(text);

    // Choose from the providers that are actually configured. Cheap, fast models
    // handle ordinary and memory-backed synthesis; specialist tasks get a capable
    // candidate first. The normal fallback chain still applies after this choice.
    const candidates = (ids) => {
        const available = ids.filter(id => isConfigured(getModel(id)) && adapters[id]);
        const priced = available.map((id, order) => ({ id, order, rates: getModelRates(id) }))
            .filter(item => item.rates)
            .sort((a, b) => (a.rates.inputUsdPerMillion + a.rates.outputUsdPerMillion) - (b.rates.inputUsdPerMillion + b.rates.outputUsdPerMillion) || a.order - b.order);
        return priced[0]?.id || available[0];
    };
    if (deepReasoning) return candidates(['chatgpt', 'kimi', 'claude-haiku', 'gemini-flash', 'grok-ai']) || 'gemini-flash';
    if (longDocument) return candidates(['kimi', 'gemini-flash', 'chatgpt', 'claude-haiku']) || 'gemini-flash';
    if (codeTask) return candidates(['claude-haiku', 'chatgpt', 'gemini-flash', 'kimi']) || 'gemini-flash';
    if (structuredTask || memoryRelevant) return candidates(['gemini-flash', 'nemotron', 'llama', 'chatgpt', 'claude-haiku']) || 'gemini-flash';
    return candidates(['gemini-flash', 'nemotron', 'llama', 'claude-haiku', 'chatgpt']) || 'gemini-flash';
}

function normalizeUsage(usage = {}) {
    const safeCount = value => {
        const count = Number(value);
        return Number.isFinite(count) && count > 0 ? Math.round(count) : 0;
    };
    return {
        inputTokens: safeCount(usage.promptTokenCount ?? usage.prompt_tokens ?? usage.input_tokens ?? 0),
        outputTokens: safeCount(usage.candidatesTokenCount ?? usage.completion_tokens ?? usage.output_tokens ?? 0)
    };
}

function estimateCost(modelId, usage) {
    const rates = getModelRates(modelId);
    if (!rates) return null;
    return (usage.inputTokens * rates.inputUsdPerMillion + usage.outputTokens * rates.outputUsdPerMillion) / 1_000_000;
}

export async function chat({ messages, memory = '', modelId = 'gemini-flash', stream = false, auto = false, allowFallback = true }) {
    const requestedModel = auto || modelId === 'auto' ? selectAutoModel(messages.at(-1)?.content || '', memory) : modelId;
    const chosen = getModel(requestedModel);
    if (!chosen) throw new Error('Selected model is not available.');
    const candidates = [requestedModel, ...(allowFallback ? chosen.fallback : [])]
        .filter((value, index, list) => list.indexOf(value) === index)
        .filter(value => isConfigured(getModel(value)) && adapters[value]);
    if (!candidates.length) throw new Error(`No configured model is available for ${chosen.displayName}.`);
    const errors = [];
    for (const candidateId of candidates) {
        try {
            const result = await adapters[candidateId]({ messages, memory, stream, modelId: candidateId });
            const usage = normalizeUsage(result.usage);
            return {
                ...result,
                requestedModel,
                fallback: candidateId !== requestedModel,
                usage: { ...usage, estimatedCostUsd: estimateCost(candidateId, usage) }
            };
        } catch (error) {
            errors.push(`${candidateId}: ${error instanceof Error ? error.message : 'provider error'}`);
        }
    }
    throw new Error(errors.join('; ') || 'No model provider could complete this request.');
}

export { MODEL_REGISTRY } from './registry.js';
