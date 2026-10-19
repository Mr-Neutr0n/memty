const mongoose = require('mongoose');
const memoryConnection = mongoose.connection.useDb(process.env.MEMORY_DATABASE || 'Memory', { useCache: true });

const messageSchema = new mongoose.Schema({
    role: { type: String, enum: ['user', 'assistant'], required: true },
    content: { type: String, required: true, maxlength: 30000 },
    model: { type: String, default: '' },
    memoryUsed: { type: [{ id: String, fact: String, type: String }], default: [] },
    createdAt: { type: Date, default: Date.now },
}, { _id: false });

const conversationSchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    conversationId: { type: String, required: true, maxlength: 80 },
    title: { type: String, maxlength: 120, default: 'New conversation' },
    messages: { type: [messageSchema], default: [] },
    workingSummary: { type: String, maxlength: 6000, default: '' },
    episodeSummary: { type: String, maxlength: 2000, default: '' },
    messageCount: { type: Number, default: 0 },
    lastModel: { type: String, default: '' },
    usage: { type: [{ model: String, inputTokens: Number, outputTokens: Number, estimatedCostUsd: Number }], default: [] },
}, { timestamps: true });

conversationSchema.index({ userId: 1, conversationId: 1 }, { unique: true });
conversationSchema.index({ userId: 1, updatedAt: -1 });
module.exports = memoryConnection.models.MemoryConversation || memoryConnection.model('MemoryConversation', conversationSchema, 'user_conversations');
