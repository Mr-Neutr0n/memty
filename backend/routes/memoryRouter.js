const express = require('express');
const catchAsync = require('../controller/catchAsync');
const { requireSession } = require('../utils/session');
const memoryService = require('../utils/memoryService');
const Conversation = require('../model/conversationModel');

const router = express.Router();
router.use(requireSession);

router.get('/', catchAsync(async (req, res) => {
    const memories = await memoryService.listMemories(req.userId, req.query.archived === 'true');
    res.set('Cache-Control', 'no-store').json({ status: 'success', data: { memories } });
}));

router.get('/conversations', catchAsync(async (req, res) => {
    const conversations = await memoryService.listConversations(req.userId);
    res.set('Cache-Control', 'no-store').json({ status: 'success', data: { conversations } });
}));

router.get('/conversation/:conversationId', catchAsync(async (req, res) => {
    const conversation = await memoryService.getConversation(req.userId, req.params.conversationId);
    if (!conversation) return res.status(404).json({ status: 'fail', message: 'Conversation not found.' });
    res.set('Cache-Control', 'no-store').json({ status: 'success', data: { conversation } });
}));

router.delete('/conversations', catchAsync(async (req, res) => {
    await memoryService.deleteConversations(req.userId);
    res.status(204).end();
}));

router.get('/usage', catchAsync(async (req, res) => {
    const usage = await memoryService.listUsage(req.userId);
    res.set('Cache-Control', 'no-store').json({ status: 'success', data: { usage } });
}));

router.post('/', catchAsync(async (req, res) => {
    try {
        const memory = await memoryService.createMemory(req.userId, req.body || {});
        res.status(201).json({ status: 'success', data: { memory } });
    } catch (error) {
        return res.status(400).json({ status: 'fail', message: error.message });
    }
}));

router.post('/context', catchAsync(async (req, res) => {
    const { conversationId, query, contextWindow, provider } = req.body || {};
    if (typeof conversationId !== 'string' || typeof query !== 'string' || query.length > 4000 || (contextWindow !== undefined && (!Number.isInteger(contextWindow) || contextWindow < 1024 || contextWindow > 2000000))) {
        return res.status(400).json({ status: 'fail', message: 'A conversation ID and query of at most 4,000 characters are required.' });
    }
    const context = await memoryService.getContext(req.userId, { conversationId, query, contextWindow, provider });
    res.set('Cache-Control', 'no-store').json({ status: 'success', data: context });
}));

router.post('/commit', catchAsync(async (req, res) => {
    const result = await memoryService.commitTurn(req.userId, req.body || {});
    res.set('Cache-Control', 'no-store').json({ status: 'success', data: result });
}));

router.patch('/:id', catchAsync(async (req, res) => {
    const memory = await memoryService.editMemory(req.userId, req.params.id, req.body || {});
    if (!memory) return res.status(404).json({ status: 'fail', message: 'Memory not found.' });
    res.json({ status: 'success', data: { memory } });
}));

router.delete('/:id', catchAsync(async (req, res) => {
    const deleted = await memoryService.deleteMemory(req.userId, req.params.id);
    if (!deleted) return res.status(404).json({ status: 'fail', message: 'Memory not found.' });
    res.status(204).end();
}));

router.delete('/conversation/:conversationId', catchAsync(async (req, res) => {
    const deleted = await Conversation.deleteOne({ userId: req.userId, conversationId: req.params.conversationId });
    res.status(deleted.deletedCount ? 204 : 404).end();
}));

module.exports = router;
