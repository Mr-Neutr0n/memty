const mongoose = require('mongoose');
const validator = require('validator');
const bcrypt = require('bcrypt');

const userSchema = new mongoose.Schema({
    name: {
        type: String,
        required: [true, 'Please enter your name'],
        trim: true,
        minlength: 2,
        maxlength: 100
    },
    email: {
        type: String,
        required: [true, 'Please enter your email'],
        lowercase: true,
        trim: true,
        unique: true,
        validate: [validator.isEmail, 'Enter a valid email']
    },
    DOB: {
        type: String,
        trim: true,
        maxlength: 10,
        default: ''
    },
    avatarData: {
        type: String,
        maxlength: 80000,
        default: ''
    },
    preferredPaymentMethod: {
        type: String,
        enum: ['', 'upi', 'card'],
        default: ''
    },
    password: {
        type: String,
        minlength: 8,
        select: false
    },
    googleId: {
        type: String,
        unique: true,
        sparse: true,
        select: false
    },
    plan: {
        type: String,
        enum: ['free', 'pro'],
        default: 'free'
    },
}, { timestamps: true });

userSchema.pre('save', async function hashPassword(next) {
    if (!this.isModified('password') || !this.password) return next();
    this.password = await bcrypt.hash(this.password, 12);
    next();
});

userSchema.methods.correctPassword = function correctPassword(candidate, hashed) {
    return bcrypt.compare(candidate, hashed);
};

userSchema.methods.toSafeObject = function toSafeObject() {
    const user = this.toObject();
    delete user.password;
    delete user.googleId;
    delete user.__v;
    return user;
};

module.exports = mongoose.model('User', userSchema, 'login');
