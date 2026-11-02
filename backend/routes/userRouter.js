const express = require('express');
const authController = require('../controller/authController');
const { requireSession } = require('../utils/session');

const router = express.Router();

function requireTrustedOrigin(req, res, next) {
    const origin = req.get('origin');
    const allowedOrigins = (process.env.CORS_ORIGIN || 'http://localhost:3001')
        .split(',').map(value => value.trim()).filter(Boolean);
    if (!origin || !allowedOrigins.includes(origin)) {
        return res.status(403).json({ status: 'fail', message: 'Google sign-in must come from the configured Memty site.' });
    }
    next();
}

router.post('/signup', authController.signup);
router.post('/login', authController.login);
router.post('/signIN', authController.login);
router.post('/google', requireTrustedOrigin, authController.google);
router.get('/me', requireSession, authController.me);
router.patch('/me', requireSession, authController.updateMe);
router.post('/logout', authController.logout);

module.exports = router;
