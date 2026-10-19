const express = require('express');
const authController = require('../controller/authController');
const { requireSession } = require('../utils/session');

const router = express.Router();

router.post('/signup', authController.signup);
router.post('/login', authController.login);
router.post('/signIN', authController.login);
router.post('/google', authController.google);
router.get('/me', requireSession, authController.me);
router.post('/logout', authController.logout);

module.exports = router;
