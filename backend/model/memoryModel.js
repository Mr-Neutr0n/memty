const mongoose = require('mongoose');
const memoryConnection = mongoose.connection.useDb(process.env.MEMORY_DATABASE || 'Memory', { useCache: true });

const memorySchema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },
    fact: { type: String, required: true, trim: true, maxlength: 500 },
    type: { type: String, enum: ['semantic', 'style'], required: true, index: true },
    confidence: { type: Number, min: 0, max: 1, default: 0.8 },
    importance: { type: Number, min: 0, max: 1, default: 0.5 },
    sourceMessage: { type: String, maxlength: 2000, default: '' },
    pinned: { type: Boolean, default: false },
    status: { type: String, enum: ['active', 'archived'], default: 'active', index: true },
    supersededBy: { type: mongoose.Schema.Types.ObjectId, ref: 'Memory', default: null },
    embedding: { type: [Number], select: false, default: undefined },
    useCount: { type: Number, default: 0 },
    lastUsedAt: { type: Date, default: Date.now },
}, { timestamps: true });

memorySchema.index({ userId: 1, status: 1, updatedAt: -1 });
module.exports = memoryConnection.models.Memory || memoryConnection.model('Memory', memorySchema, 'user_memories');
