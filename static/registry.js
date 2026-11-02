export const MODEL_REGISTRY = [
    {
        id: 'gemini-flash',
        displayName: 'Gemini Flash',
        provider: 'Google',
        description: 'Fast, efficient, and capable for general tasks and reasoning.',
        capabilities: ['Text', 'Code', 'Reasoning'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M12,22.5c-0.3,0-0.5-0.1-0.7-0.3c-2.3-2.6-4.9-4.8-7.7-6.5C3.3,15.5,3,15.2,3,14.8c0-0.4,0.3-0.8,0.7-0.9c2.8-1.7,5.4-3.9,7.7-6.5c0.3-0.4,1-0.4,1.3,0c2.3,2.6,4.9,3.9,7.7,6.5c0.4,0.2,0.7,0.5,0.7,0.9c0,0.4-0.3,0.7-0.7,0.9c-2.8,1.7-4.9,3.9-7.7,6.5C12.5,22.4,12.3,22.5,12,22.5z"/></svg>`
    },
    {
        id: 'grok-ai',
        displayName: 'Grok AI',
        provider: 'xAI',
        description: 'Conversational intelligence with a direct, curious style.',
        capabilities: ['Text', 'Code', 'Reasoning'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M20.4 4.6a1 1 0 0 0-1.4 0l-7.6 7.6-2.1-2.1a1 1 0 1 0-1.4 1.4l2.8 2.8a1 1 0 0 0 1.4 0L20.4 6a1 1 0 0 0 0-1.4ZM5.2 5.2A6.8 6.8 0 1 0 12 2.4a1 1 0 1 0 0 2 4.8 4.8 0 1 1-4.8 4.8 1 1 0 0 0-2 0 6.8 6.8 0 0 0 0 0Z"/></svg>`
    },
    {
        id: 'claude-haiku',
        displayName: 'Claude Haiku',
        provider: 'Anthropic',
        description: 'Fast, capable responses for everyday questions and coding.',
        capabilities: ['Text', 'Code', 'Vision'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M19.1 5.9L12 2 4.9 5.9v7.7L12 22l7.1-4.4V5.9zM12 19l-5-3.1V8.2l5-2.8 5 2.8v7.7L12 19z"/></svg>`
    },
    {
        id: 'nemotron',
        displayName: 'NVIDIA Nemotron',
        provider: 'NVIDIA',
        description: 'High-performance AI model optimized for complex workloads.',
        capabilities: ['Text', 'Code'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M12.986 4.706V2.32H6.551v19.467h6.435V9.453H11.59v10.518H8.384V4.706h4.602zM17.433 2.32h-3.415v19.467h3.415V2.32z"/></svg>`
    },
    {
        id: 'chatgpt',
        displayName: 'ChatGPT',
        provider: 'OpenAI',
        description: 'Fast, versatile AI for writing, reasoning, and coding.',
        capabilities: ['Text', 'Code', 'Reasoning'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M21.3 10.2a5.7 5.7 0 0 0-5.5-4.3A5.7 5.7 0 0 0 5.2 8.2a5.7 5.7 0 0 0 1.1 8.1 5.7 5.7 0 0 0 5.5 4.3 5.7 5.7 0 0 0 5.6-2.3 5.7 5.7 0 0 0 3.9-8.1Z"/></svg>`
    },
    {
        id: 'kimi',
        displayName: 'Moonshot AI Kimi',
        provider: 'Moonshot AI',
        description: 'Long-context model excellent for document analysis.',
        capabilities: ['Text', 'Long Context'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10c1.33 0 2.6-.26 3.78-.73-3.66-1.57-6.28-5.18-6.28-9.27 0-4.09 2.62-7.7 6.28-9.27C14.6 2.26 13.33 2 12 2z"/></svg>`
    },
    {
        id: 'llama',
        displayName: 'Meta Llama',
        provider: 'Meta',
        description: 'Open-source powerhouse for diverse applications.',
        capabilities: ['Text', 'Code'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M18.8 6.4C18 5.6 17 5 16 5s-2 .6-2.8 1.4L12 7.6 10.8 6.4C10 5.6 9 5 8 5s-2 .6-2.8 1.4C4.4 7.2 4 8 4 9s.4 1.8 1.2 2.6L12 18.4l6.8-6.8c.8-.8 1.2-1.6 1.2-2.6s-.4-1.8-1.2-2.6z"/></svg>`
    },
    {
        id: 'auto',
        displayName: 'Memty Auto',
        provider: 'Memty Router',
        description: 'Automatically route code, long documents, and quick questions to a suitable configured model.',
        capabilities: ['Text', 'Code', 'Routing'],
        available: true,
        proOnly: false,
        integrated: true,
        icon: `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M12 2a10 10 0 1 0 10 10h-2a8 8 0 1 1-8-8V2Zm1 0v10l7.1-7.1A9.97 9.97 0 0 0 13 2Z"/></svg>`
    }
];

export function getModel(id) {
    return MODEL_REGISTRY.find(m => m.id === id);
}

export function getAvailableModels() {
    return MODEL_REGISTRY.filter(m => m.available);
}

export function getAllModels() {
    return MODEL_REGISTRY;
}
