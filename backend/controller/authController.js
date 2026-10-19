const { OAuth2Client } = require('google-auth-library');
const User = require('../model/userModel');
const catchAsync = require('./catchAsync');
const { setSessionCookie, clearSessionCookie } = require('../utils/session');

const googleClient = process.env.GOOGLE_CLIENT_ID
    ? new OAuth2Client(process.env.GOOGLE_CLIENT_ID)
    : null;

const sendAuthResponse = (res, user, status = 200) => {
    setSessionCookie(res, user._id);
    res.status(status).json({
        status: 'success',
        data: { user: user.toSafeObject() }
    });
};

exports.me = catchAsync(async (req, res) => {
    const user = await User.findById(req.userId);
    if (!user) return res.status(401).json({ status: 'fail', message: 'Account not found.' });
    res.json({ status: 'success', data: { user: user.toSafeObject() } });
});

exports.logout = (req, res) => {
    clearSessionCookie(res);
    res.status(204).end();
};

exports.signup = catchAsync(async (req, res) => {
    const { name, email, password, DOB } = req.body;
    if (typeof name !== 'string' || typeof email !== 'string' || typeof password !== 'string' || password.length < 8) {
        return res.status(400).json({ status: 'fail', message: 'Name, email, and a password of at least 8 characters are required' });
    }
    const user = await User.create({ name, email, password, DOB });
    sendAuthResponse(res, user, 201);
});

exports.login = catchAsync(async (req, res) => {
    const { email, password } = req.body;
    if (typeof email !== 'string' || typeof password !== 'string' || !email.trim() || !password) {
        return res.status(400).json({ status: 'fail', message: 'Email and password are required' });
    }
    const user = await User.findOne({ email: email.toLowerCase().trim() }).select('+password');
    if (!user || !user.password || !(await user.correctPassword(password, user.password))) {
        return res.status(401).json({ status: 'fail', message: 'Invalid email or password' });
    }
    sendAuthResponse(res, user);
});

exports.google = catchAsync(async (req, res) => {
    if (!googleClient) {
        return res.status(503).json({ status: 'fail', message: 'Google login is not configured' });
    }
    const { credential } = req.body;
    if (!credential) return res.status(400).json({ status: 'fail', message: 'Google credential is required' });

    const ticket = await googleClient.verifyIdToken({
        idToken: credential,
        audience: process.env.GOOGLE_CLIENT_ID
    });
    const payload = ticket.getPayload();
    if (!payload || !payload.email || !payload.email_verified) {
        return res.status(401).json({ status: 'fail', message: 'Google account could not be verified' });
    }

    let user = await User.findOne({ email: payload.email.toLowerCase() });
    if (!user) {
        user = await User.create({
            name: payload.name || payload.email.split('@')[0],
            email: payload.email,
            googleId: payload.sub
        });
    } else if (!user.googleId) {
        user.googleId = payload.sub;
        await user.save();
    }
    sendAuthResponse(res, user);
});

// Backward-compatible endpoint name used by older clients.
exports.signIN = exports.login;
