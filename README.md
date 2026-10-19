# NexorAI

NexorAI is a multi-provider AI workspace built with Next.js, an Express authentication and memory service, and MongoDB. It lets signed-in users switch models while NexorAI keeps conversation context and user-controlled memories independently of the model provider.

## Contents

- [What the app includes](#what-the-app-includes)
- [Architecture](#architecture)
- [Run locally](#run-locally)
- [Environment configuration](#environment-configuration)
- [MongoDB setup](#mongodb-setup)
- [Production notes](#production-notes)
- [Detailed guides](#detailed-guides)

## What the app includes

- Landing page with model and feature overview.
- Sign-in, account registration, and optional Google sign-in.
- Chat workspace with model selection, Auto routing, fallback, side-by-side compare, local history controls, light/dark theme, and mobile sidebar.
- Portable memory dashboard to inspect, add, edit, pin, and delete facts; view archived facts and conversation summaries; delete saved conversations; and review usage counts.
- Provider availability and model metadata at `/api/config`.
- Terms, privacy, and first-party API reference pages.
- Express API for authentication, signed sessions, conversations, memory retrieval, and usage data.

Model/provider availability depends on credentials and current provider access. The interface does not imply that every provider key is configured.

## Architecture

```text
Browser
  └─ Next.js app (port 3001)
       ├─ Pages, chat API, model adapters, local browser history
       └─ private proxy (PROXY_TARGET)
            └─ Express service (port 3002)
                 ├─ signed HTTP-only account sessions
                 └─ MongoDB: Users + Memory databases
```

The root `app/` contains the Next.js routes. Older landing, login, and chat markup is served through `components/legacy-page.tsx` and receives its styling from `app/globals.css`. `providers/` normalizes the model calls. `backend/` contains the Express app and MongoDB services. See the component guides below for details.

## Requirements

- Node.js 20.9 or later
- npm
- MongoDB (MongoDB Atlas is recommended for Atlas Vector Search)

## Run locally

Install dependencies in both packages:

```powershell
npm install
cd backend
npm install
```

Create the root `.env` from `.env.example` and `backend/.env` from `backend/.env.example`. Fill in the MongoDB URI and any model/provider credentials you plan to use. Keep both populated files private; they are ignored by Git.

Run the frontend and backend in separate terminals:

```powershell
# Terminal 1, repository root
npm run dev
```

```powershell
# Terminal 2
cd backend
npm run dev
```

Open [http://localhost:3001](http://localhost:3001). The API backend listens on port 3002 by default. Sign-in, chat memory, and the Memory page need the backend and a reachable MongoDB server.

`npm start` starts the built Next.js production server. Build first with `npm run build`. Do not pass `frontend:dev` to `npm start`; to run development, use `npm run dev` or `npm run frontend:dev`.

## Environment configuration

The root `.env` configures Next.js and the model adapters. `backend/.env` configures MongoDB and the Express service; the backend also loads the root environment first. Common settings:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Frontend and backend | Gemini chat, memory extraction, summaries, and embeddings |
| `CLAUDE_API_KEY` | Frontend | Claude adapter |
| `GROK_API_KEY` | Frontend | Grok adapter |
| `KIMI_API_KEY` | Frontend | Kimi adapter |
| `OPEN_ROUTER_OPEN_API_KEYS` | Frontend | ChatGPT-compatible OpenRouter adapter |
| `OPEN_ROUTER_API_KEY` | Frontend | NVIDIA Nemotron and Meta Llama via OpenRouter |
| `MONGO_URI` | Backend | MongoDB connection string |
| `MONGO_DATABASE` | Backend | Account database; defaults to `Users` |
| `MEMORY_DATABASE` | Backend | Portable-memory database; defaults to `Memory` |
| `SESSION_SECRET` | Backend | Stable, high-entropy signing key; required in production |
| `PROXY_TARGET` | Frontend | Private backend URL; defaults to `http://localhost:3002` |
| `PORT` | Each service | Frontend defaults to 3001; backend defaults to 3002 |
| `MEMORY_VECTOR_INDEX` | Backend | Atlas vector index name; defaults to `memory_vector_index` |

See `.env.example` and `backend/.env.example` for the full variable list, model IDs, timeouts, and optional usage-rate settings. Never paste real secrets into issues, documentation, or source control.

## MongoDB setup

Set `MONGO_URI`, `MONGO_DATABASE=Users`, and `MEMORY_DATABASE=Memory` in `backend/.env`. On startup the backend creates `user_memories`, `user_conversations`, and `model_usage` in the `Memory` database if needed. Existing collections such as `Memory.messages` are left intact. Account documents remain in `Users`.

For semantic vector retrieval, create the Atlas Search vector index on `Memory.user_memories` using [`backend/memory-vector-index.json`](backend/memory-vector-index.json). The configured index needs 768-dimensional cosine vectors and filters for `userId` and `status`. Without the index or embedding service, memory retrieval can fall back to lexical and recency scoring.

## Production notes

- Deploy the frontend and backend as separate services. Keep MongoDB private and the backend accessible only through the trusted proxy/network path.
- Set a stable high-entropy `SESSION_SECRET` in the backend production environment. Do not rely on a process-random development secret.
- Configure `PROXY_TARGET`, allowed `CORS_ORIGIN`, provider credentials, MongoDB, and health checks for the deployed environment.
- The chat rate limit is in-memory and per frontend process; it is not shared across instances. Add a shared limiter, account quotas, monitoring, backups, and an account deletion/retention process before public launch.
- Cost estimates require operator-configured per-model token rates. They are estimates, not billing records.
- Chat responses are not streamed. Auto routing uses basic request heuristics. Provider fallbacks and compare mode depend on configured providers.
- Review the Privacy Notice and Terms against the actual legal entity, provider agreements, data retention, and deployment before release.

## Detailed guides

- [Frontend and mobile layout](app/README.md)
- [Backend and MongoDB](backend/README.md)
- [Portable memory](app/memory/README.md)
- [Model providers and routing](providers/README.md)
- [Package scripts](package.json) and [backend scripts](backend/package.json)
