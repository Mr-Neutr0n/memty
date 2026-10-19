const histories = new Map();

export function getConversation(userId, provider) {
    return histories.get(`${userId}:${provider}`) || [];
}

export function saveConversation(userId, provider, history, maxMessages = 40) {
    histories.set(`${userId}:${provider}`, history.slice(-maxMessages));
}

export function clearConversation(userId, provider) {
    histories.delete(`${userId}:${provider}`);
}
