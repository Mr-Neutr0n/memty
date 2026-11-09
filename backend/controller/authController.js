const { OAuth2Client } = require('google-auth-library');
const User = require('../model/userModel');
const catchAsync = require('./catchAsync');
const { setSessionCookie, clearSessionCookie } = require('../utils/session');
const { validateDateOfBirth } = require('../utils/dateOfBirth');

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

exports.updateMe = catchAsync(async (req, res) => {
    const body = req.body || {};
    const allowedKeys = ['name', 'DOB', 'avatarData', 'preferredPaymentMethod'];
    if (!allowedKeys.some(key => Object.prototype.hasOwnProperty.call(body, key))) {
        return res.status(400).json({ status: 'fail', message: 'No profile changes were provided.' });
    }

    const updates = {};
    if (Object.prototype.hasOwnProperty.call(body, 'name')) {
        if (typeof body.name !== 'string' || body.name.trim().length < 2 || body.name.trim().length > 100) {
            return res.status(400).json({ status: 'fail', message: 'Name must be between 2 and 100 characters.' });
        }
        updates.name = body.name.trim();
    }
    if (Object.prototype.hasOwnProperty.call(body, 'DOB')) {
        const dobError = validateDateOfBirth(body.DOB);
        if (dobError) return res.status(400).json({ status: 'fail', message: dobError });
        updates.DOB = body.DOB;
    }
    if (Object.prototype.hasOwnProperty.call(body, 'avatarData')) {
        if (typeof body.avatarData !== 'string' || body.avatarData.length > 80000 ||
            (body.avatarData && !/^data:image\/(?:webp|jpeg|png);base64,[A-Za-z0-9+/]+={0,2}$/.test(body.avatarData))) {
            return res.status(400).json({ status: 'fail', message: 'Profile image must be a JPEG, PNG, or WebP image under 60 KB.' });
        }
        updates.avatarData = body.avatarData;
    }
    if (Object.prototype.hasOwnProperty.call(body, 'preferredPaymentMethod')) {
        if (!['', 'upi', 'card'].includes(body.preferredPaymentMethod)) {
            return res.status(400).json({ status: 'fail', message: 'Choose UPI or card as your preferred payment method.' });
        }
        updates.preferredPaymentMethod = body.preferredPaymentMethod;
    }

    const user = await User.findByIdAndUpdate(req.userId, { $set: updates }, { new: true, runValidators: true });
    if (!user) return res.status(404).json({ status: 'fail', message: 'Account not found.' });
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
    if (Object.prototype.hasOwnProperty.call(req.body, 'DOB')) {
        const dobError = validateDateOfBirth(DOB);
        if (dobError) return res.status(400).json({ status: 'fail', message: dobError });
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
    const { credential } = req.body || {};
    if (typeof credential !== 'string' || credential.length < 20 || credential.length > 10000) {
        return res.status(400).json({ status: 'fail', message: 'A valid Google credential is required' });
    }

    let ticket;
    try {
        ticket = await googleClient.verifyIdToken({
            idToken: credential,
            audience: process.env.GOOGLE_CLIENT_ID
        });
    } catch {
        return res.status(401).json({ status: 'fail', message: 'Google account could not be verified' });
    }
    const payload = ticket.getPayload();
    if (!payload || typeof payload.sub !== 'string' || !payload.sub || !payload.email || payload.email_verified !== true) {
        return res.status(401).json({ status: 'fail', message: 'Google account could not be verified' });
    }

    const email = payload.email.toLowerCase().trim();
    let user = await User.findOne({ googleId: payload.sub }).select('+googleId');
    if (user) return sendAuthResponse(res, user);

    user = await User.findOne({ email }).select('+googleId +password');
    const hostedDomain = typeof payload.hd === 'string' ? payload.hd.toLowerCase() : '';
    const googleControlsEmail = email.endsWith('@gmail.com') || Boolean(hostedDomain && email.endsWith(`@${hostedDomain}`));

    if (user?.googleId && user.googleId !== payload.sub) {
        return res.status(409).json({ status: 'fail', message: 'This email is linked to another Google account. Sign in with your existing method.' });
    }
    if (user && !user.googleId && !googleControlsEmail) {
        return res.status(409).json({ status: 'fail', message: 'An account already uses this email. Sign in with your password first before linking Google.' });
    }

    if (!user) {
        try {
            const googleName = typeof payload.name === 'string' ? payload.name.trim() : '';
            user = await User.create({
                name: googleName.length >= 2 && googleName.length <= 100 ? googleName : email.split('@')[0],
                email,
                googleId: payload.sub
            });
        } catch (error) {
            if (error.code !== 11000) throw error;
            user = await User.findOne({ googleId: payload.sub }).select('+googleId');
            if (!user) return res.status(409).json({ status: 'fail', message: 'An account with this email already exists. Sign in with your existing method.' });
        }
    } else if (!user.googleId) {
        user.googleId = payload.sub;
        try {
            await user.save();
        } catch (error) {
            if (error.code !== 11000) throw error;
            user = await User.findOne({ googleId: payload.sub }).select('+googleId');
            if (!user) return res.status(409).json({ status: 'fail', message: 'This account was linked to a different Google sign-in. Please try again.' });
        }
    }
    sendAuthResponse(res, user);
});

// Backward-compatible endpoint name used by older clients.
exports.signIN = exports.login;
