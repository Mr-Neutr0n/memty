import { GoogleGenerativeAI } from '@google/generative-ai';

let client;
export async function chat({ messages, memory = '', stream = false, modelId = 'gemini-flash' }) {
    if (stream) throw new Error('Streaming is not available yet.');
    if (!process.env.GEMINI_API_KEY) throw new Error('Gemini is not configured.');
    client ||= new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
    const model = client.getGenerativeModel({
        model: process.env.GEMINI_MODEL || 'gemini-2.5-flash',
        systemInstruction: `${BASE_PROMPT}${memory ? `\n\n${memory}` : ''}`
    });
    const history = messages.slice(0, -1).map(message => ({ role: message.role === 'assistant' ? 'model' : 'user', parts: [{ text: message.content }] }));
    const result = await model.startChat({ history, generationConfig: { maxOutputTokens: Number(process.env.GEMINI_MAX_OUTPUT_TOKENS || 4096) } }).sendMessage(messages.at(-1)?.content || '');
    const response = await result.response;
    const text = response.text();
    if (!text?.trim()) throw new Error('Gemini returned an empty response.');
    return { text, model: modelId, usage: response.usageMetadata || null };
}

const BASE_PROMPT = 'You are a helpful, accurate AI assistant. Be clear and practical. The user may switch models; treat the supplied neutral chat history as the shared conversation.';
