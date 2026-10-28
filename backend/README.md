# Backend guide

The backend is an Express service that handles account authentication, signed sessions, portable memory, persisted neutral conversations, and per-model usage. It runs independently of Next.js and listens on port 3002 by default.

> **Request path:** the Next.js app proxies trusted account and memory requests to this service. The browser does not connect directly to Express. See the root [architecture diagram](../README.md#how-it-fits-together).

| Looking for... | Guide |
| --- | --- |
| Chat request and model selection | [Frontend chat route](../app/README.md) · [Provider adapters](../providers/README.md) |
| Memory behavior and storage | [Portable memory guide](../app/memory/README.md) |
| Optional Python vault | [SmartMemory guide](../SmartMemory/README.md) |

## Code map

| Path | Responsibility |
| --- | --- |
| `server.js`, `app.js` | Start the HTTP server and configure Express middleware/routes. |
| `routes/` | Account and memory HTTP endpoints. |
| `controller/` | Authentication handlers and shared async/error helpers. |
| `model/` | MongoDB models for accounts, memories, conversations, and usage. |
| `utils/session.js` | Signed session cookie handling and authentication middleware. |
| `utils/memoryService.js` | Memory retrieval, persistence, and optional Vault bridge. |

## Run

From the repository root:

```powershell
cd backend
npm install
npm run dev
```

`npm start` runs the backend without nodemon. The frontend is a separate process; start it from the repository root with `npm run dev`.

## Configuration

Copy `backend/.env.example` to `backend/.env`. Set `MONGO_URI` to the Atlas connection string, `MONGO_DATABASE=Users`, `MEMORY_DATABASE=Memory`, and a stable high-entropy `SESSION_SECRET` for production. Set the backend port and CORS origin to match deployment. Google sign-in uses `GOOGLE_CLIENT_ID` when enabled. Keep secrets out of Git.

The service also loads the root `.env` first, then `backend/.env` overrides it. Provider requests and memory extraction need the relevant keys in the environment accessible to the service that makes those requests.

## MongoDB databases and collections

- `Users`: account documents from `model/userModel.js`.
- `Memory.user_memories`: user-managed semantic facts and answer-style preferences.
- `Memory.user_conversations`: neutral chat messages, working summary, episode summary, and conversation usage.
- `Memory.model_usage`: aggregated per-user, per-model request and token counts.

The backend creates the three memory collections on startup. It does not delete or replace existing collections such as `Memory.messages`. The Atlas Vector Search index is separately configured from `memory-vector-index.json` on `Memory.user_memories`.

## Routes

All account routes are mounted at `/users`; memory routes are mounted at `/memory`. The memory router requires a valid signed session.

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/users/signup` | Create account and issue session cookie |
| `POST` | `/users/login` | Authenticate and issue session cookie |
| `POST` | `/users/google` | Verify Google credential and issue session cookie |
| `GET` / `PATCH` | `/users/me` | Read the authenticated account or update its name, date of birth, resized avatar, and billing preference |
| `POST` | `/users/logout` | Clear session cookie |
| `GET` | `/memory` | List active or archived memories |
| `POST` | `/memory` | Add a memory |
| `PATCH` / `DELETE` | `/memory/:id` | Edit or delete a memory |
| `GET` | `/memory/conversations` | List saved conversation summaries |
| `GET` | `/memory/conversation/:id` | Read one user's conversation |
| `DELETE` | `/memory/conversations` | Delete all saved conversations for the user |
| `DELETE` | `/memory/conversation/:id` | Delete one saved conversation |
| `GET` | `/memory/usage` | List per-model usage |
| `POST` | `/memory/context` | Retrieve conversation and relevant memory brief |
| `POST` | `/memory/commit` | Save a completed chat turn and update memory/usage |
| `GET` | `/health` | Report backend and MongoDB readiness |

## Operations and security notes

The Express app waits for MongoDB before listening and reports `503` from `/health` until connected. Sessions are signed in the backend and stored in HTTP-only cookies. Production must use a stable secret, HTTPS, the correct cookie/security settings, private backend networking, MongoDB access controls, backups, and monitored logs.

Before exposing the service publicly, review account deletion, data retention, abuse protection, shared rate limits, request logging, and incident response. The existing frontend rate limit is not a backend-wide/shared quota. Do not assume this app has been audited or certified.

