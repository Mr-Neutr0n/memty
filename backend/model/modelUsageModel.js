const mongoose = require('mongoose');
const memoryConnection = mongoose.connection.useDb(process.env.MEMORY_DATABASE || 'Memory', { useCache: true });

const schema = new mongoose.Schema({
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    model: { type: String, required: true },
    requestCount: { type: Number, default: 0 },
    inputTokens: { type: Number, default: 0 },
    outputTokens: { type: Number, default: 0 },
    estimatedCostUsd: { type: Number, default: 0 },
    costTrackedRequests: { type: Number, default: 0 },
}, { timestamps: true });

schema.index({ userId: 1, model: 1 }, { unique: true });
module.exports = memoryConnection.models.ModelUsage || memoryConnection.model('ModelUsage', schema, 'model_usage');
