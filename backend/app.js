const express = require('express');
const morgan = require('morgan');
const mongoose = require('mongoose');
const dotenv = require('dotenv');
const cors = require('cors');
const path = require('path');
const dns = require('dns');

dotenv.config({ path: path.join(__dirname, '..', '.env') });
dotenv.config({ path: path.join(__dirname, '.env'), override: true });

const userRouter = require('./routes/userRouter');
const memoryRouter = require('./routes/memoryRouter');
const globalErrorHandler = require('./controller/errorController');

const app = express();
app.disable('x-powered-by');
app.use(cors({
    origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',').map(origin => origin.trim()) : true
}));
app.use(express.json());
app.use(morgan(process.env.NODE_ENV === 'production' ? 'combined' : 'dev'));
app.use((req, res, next) => {
    req.requestTime = new Date().toISOString();
    next();
});

const databaseUrl = process.env.MONGO_URI || process.env.DATABASE_URL;
const DB = databaseUrl
    ? databaseUrl
        .replace('<USERNAME>', encodeURIComponent(
            process.env.DB_USERNAME || process.env.MONGO_USERNAME || process.env.USERNAME || ''
        ))
        .replace('<PASSWORD>', encodeURIComponent(process.env.DB_PASSWORD || ''))
    : '';

if (!DB) {
    console.error('MONGO_URI or DATABASE_URL must be configured in backend/.env.');
    process.exit(1);
}

let databaseReady = false;
const databaseName = process.env.MONGO_DATABASE || 'Users';

const connectDatabase = async () => {
    if (DB.startsWith('mongodb+srv://')) {
        const dnsServers = (process.env.MONGO_DNS_SERVERS || '1.1.1.1,8.8.8.8')
            .split(',')
            .map(server => server.trim())
            .filter(Boolean);
        dns.setServers(dnsServers);
        console.log(`Using DNS servers for MongoDB SRV lookup: ${dnsServers.join(', ')}`);
    }

    await mongoose.connect(DB, {
        dbName: databaseName,
        serverSelectionTimeoutMS: 10000,
        connectTimeoutMS: 10000,
        maxPoolSize: 10,
        bufferCommands: false
    });
    const memoryDatabase = mongoose.connection.useDb(process.env.MEMORY_DATABASE || 'Memory', { useCache: true });
    for (const collection of ['user_memories', 'user_conversations', 'model_usage']) {
        try { await memoryDatabase.createCollection(collection); }
        catch (error) {
            if (error.code !== 48) throw error;
        }
    }
    databaseReady = true;
    console.log(`MongoDB connected: accounts=${databaseName}, memory=${process.env.MEMORY_DATABASE || 'Memory'}`);
};

const requireDatabase = (req, res, next) => {
    if (databaseReady) return next();
    return res.status(503).json({
        status: 'fail',
        message: 'Authentication is temporarily unavailable because MongoDB is not connected.',
    });
};

//Router for the user authentication
app.use('/users', requireDatabase, userRouter);
app.use('/memory', requireDatabase, memoryRouter);

app.get('/health', (req, res) => {
    res.status(databaseReady ? 200 : 503).json({
        status: databaseReady ? 'ok' : 'degraded',
        database: databaseReady ? 'connected' : 'disconnected',
        timestamp: new Date().toISOString()
    });
});

app.use(globalErrorHandler);

const port = process.env.PORT || 3002;

const startServer = async () => {
    try {
        await connectDatabase();
        const server = app.listen(port, () => {
            console.log(`Authentication backend running on port ${port}`);
        });
        server.on('error', error => {
            if (error.code === 'EADDRINUSE') {
                console.error(
                    `Port ${port} is already in use. Stop the existing backend process or set a different PORT in backend/.env.`
                );
            } else {
                console.error('Authentication backend failed to start:', error.message);
            }
            process.exit(1);
        });

        const shutdown = async signal => {
            console.log(`${signal} received, shutting down gracefully`);
            server.close(async () => {
                await mongoose.disconnect();
                process.exit(0);
            });
        };

        process.once('SIGINT', () => shutdown('SIGINT'));
        process.once('SIGTERM', () => shutdown('SIGTERM'));
    } catch (error) {
        console.error('MongoDB connection failed:', error.message);
        if (error.message.includes('querySrv') || error.code === 'ECONNREFUSED') {
            console.error(
                'MongoDB Atlas SRV DNS lookup failed. Copy a fresh connection string from Atlas, ' +
                'confirm the cluster is running, and check your DNS/VPN/firewall settings.'
            );
        }
        process.exit(1);
    }
};

if (require.main === module) {
    startServer();
}

module.exports = { app, startServer };
