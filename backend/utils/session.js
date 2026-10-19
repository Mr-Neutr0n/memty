const crypto = require('node:crypto');

const COOKIE_NAME = 'nexor_session';
const MAX_AGE = 7 * 24 * 60 * 60;
const fallbackSecret = crypto.randomBytes(32).toString('hex');
const secret = process.env.SESSION_SECRET || fallbackSecret;

if (!process.env.SESSION_SECRET && process.env.NODE_ENV === 'production') {
    throw new Error('SESSION_SECRET must be configured in production.');
}

function sign(value) {
    return crypto.createHmac('sha256', secret).update(value).digest('base64url');
}

function createSession(userId) {
    const payload = Buffer.from(JSON.stringify({ sub: String(userId), exp: Math.floor(Date.now() / 1000) + MAX_AGE })).toString('base64url');
    return `${payload}.${sign(payload)}`;
}

function readSession(token) {
    if (typeof token !== 'string') return null;
    const [payload, signature, extra] = token.split('.');
    if (!payload || !signature || extra) return null;
    const expected = Buffer.from(sign(payload));
    const received = Buffer.from(signature);
    if (expected.length !== received.length || !crypto.timingSafeEqual(expected, received)) return null;
    try {
        const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
        if (typeof decoded.sub !== 'string' || !decoded.sub || decoded.exp <= Math.floor(Date.now() / 1000)) return null;
        return decoded.sub;
    } catch { return null; }
}

function setSessionCookie(res, userId) {
    res.cookie(COOKIE_NAME, createSession(userId), {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge: MAX_AGE * 1000
    });
}

function clearSessionCookie(res) {
    res.clearCookie(COOKIE_NAME, { httpOnly: true, secure: process.env.NODE_ENV === 'production', sameSite: 'lax', path: '/' });
}

function requireSession(req, res, next) {
    const cookieHeader = req.headers.cookie || '';
    const token = cookieHeader.split(';').map(part => part.trim()).find(part => part.startsWith(`${COOKIE_NAME}=`))?.slice(COOKIE_NAME.length + 1);
    const userId = readSession(token ? decodeURIComponent(token) : null);
    if (!userId) return res.status(401).json({ status: 'fail', message: 'Sign in to continue.' });
    req.userId = userId;
    next();
}

module.exports = { COOKIE_NAME, createSession, readSession, setSessionCookie, clearSessionCookie, requireSession };
