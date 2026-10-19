import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import { getConversation, saveConversation, clearConversation } from '../providers/conversation.js';

dotenv.config();

const SYSTEM_PROMPT = `You are a helpful AI assistant created by Rohan, a student at MS Ramaiah Institute of Technology.
You are talking to a user through a chat interface. Be friendly, helpful, clear, and concise. Preserve useful context across turns.`;
const maxTokens = Number.parseInt(process.env.GEMINI_MAX_OUTPUT_TOKENS || '4096', 10);
const maxHistory = Number.parseInt(process.env.GEMINI_MAX_HISTORY_MESSAGES || '40', 10);
const modelName = process.env.GEMINI_MODEL || 'gemini-2.5-flash';
const client = process.env.GEMINI_API_KEY
    ? new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
    : null;
const model = client?.getGenerativeModel({ model: modelName, systemInstruction: SYSTEM_PROMPT });

export async function generateGeminiResponse(userId, message) {
    if (!model) {
        throw new Error('Gemini is not configured. Set GEMINI_API_KEY and restart the server.');
    }
    const history = getConversation(userId, 'gemini');
    try {
        const chat = model.startChat({
            history,
            generationConfig: { maxOutputTokens: maxTokens > 0 ? maxTokens : 4096, temperature: 0.7 }
        });
        const result = await chat.sendMessage(message);
        const text = (await result.response).text();
        if (!text?.trim()) throw new Error('Gemini returned an empty response.');
        saveConversation(userId, 'gemini', [
            ...history,
            { role: 'user', parts: [{ text: message }] },
            { role: 'model', parts: [{ text }] }
        ], maxHistory);
        return text;
    } catch (error) {
        throw new Error(`Gemini request failed: ${error.message}`);
    }
}

export function clearGeminiConversation(userId) {
    clearConversation(userId, 'gemini');
}
