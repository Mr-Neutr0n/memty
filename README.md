<div align="center">

<img src="assets/NexorSplash.jpeg" alt="NexorAI logo" width="180" />

# NexorAI

### One workspace for multiple AI models, conversations, and portable memory.

[Explore the code](#project-map) · [Run locally](#get-started) · [Understand the architecture](#how-it-fits-together) · [Find a guide](#choose-your-path)

</div>

NexorAI is a multi-provider AI workspace built with **Next.js**, an **Express** account and memory service, **MongoDB**, and a local **Memty** memory vault. The primary memory workflow is a transparent Python CLI backed by a user-owned SQLite file; the web workspace and older MemoryPort SDK remain available as separate integrations.

This project is licensed under the [MIT License](LICENSE).

> **Project status:** provider access depends on your own credentials. Some production features are still planned; see [current limitations](#current-limitations) before deploying publicly.

## ✨ What you can do

| Chat across providers | Own memory from the CLI | Keep useful context |
| --- | --- | --- |
| Select a configured model, use fallbacks, or compare responses. | Store, inspect, recall, constrain, and delete facts with the `memty` command. | Compile deterministic, provider-filtered context without sending the whole vault to an assistant. |

The workspace also includes a responsive chat UI, model availability metadata, a memory dashboard, privacy and terms pages, and a first-party API reference. Memty is standard-library-only for Week 1: it stores atomic facts, logical constraints, rolling summaries, and raw drill-down records in `~/.memty/ledger.sqlite3`. An optional MCP adapter is available, but the CLI is the canonical way to operate the vault.

<a id="how-it-fits-together"></a>
## 🧭 How it fits together

![NexorAI system architecture: browser, Next.js, model providers, Express API, MongoDB, and optional local memory services](docs/architecture.svg)

The browser talks to the Next.js app. Its chat route calls the selected model adapter and uses a private proxy to reach the Express service for account sessions and saved data. MongoDB stores account and web-workspace memory. Memty is intentionally separate and local: the CLI owns `~/.memty/ledger.sqlite3`, and assistants consume only the compact context capsule that the user chooses to share.

### A chat request, at a glance

```mermaid
flowchart LR
    U[Your message] --> C[Next.js chat route]
    C --> M[Context and memory lookup]
    M --> R[Selected provider adapter]
    R --> A[Assistant response]
    A --> P[Persist conversation and usage]
```

<a id="get-started"></a>
## 🚀 Get started

### Requirements

- Node.js 20.9 or later and npm
- MongoDB for sign-in, saved conversations, and server-side memory
- Provider credentials for the models you want to use
- Python 3.10+ for the Memty CLI

Install the frontend and backend dependencies:

```powershell
npm install
cd backend
npm install
cd ..
```

Create local environment files and add the MongoDB URI and any provider keys you want to use:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
```

Keep populated environment files private. Open two terminals from the repository root:

```powershell
# Terminal 1: Next.js app
npm run dev
```

```powershell
# Terminal 2: Express API
cd backend
npm run dev
```

Open [http://localhost:3001](http://localhost:3001). The API listens on port `3002` by default. Sign-in and server-backed memory features need a reachable MongoDB instance. Without provider credentials, those models are shown as unavailable.

### Use the Memty CLI

Install the local package from the repository root:

```powershell
python -m pip install -e .
```

Create and inspect a user-owned vault without starting the web application:

```powershell
memty stats
memty remember project.api cache_engine "DragonflyDB" --verification USER_CONFIRMED
memty rule project.api database_queries "writing database queries" "use async Motor and project only needed fields"
memty summary project.api --set "FastAPI backend with JWT auth and MongoDB Atlas sync."
memty recall "Which cache engine should I use?" --provider claude
memty rules --namespace project.api
```

The default database is `~/.memty/ledger.sqlite3`. Use `--db C:\path\to\ledger.sqlite3` or set `MEMTY_VAULT_PATH` to select another file. `memty forget` tombstones a fact, while `memty raw-get` is the only command that reads archived raw source text.

### Start with Docker Compose

Compose starts the frontend, backend, and legacy Python Memory Vault service. MongoDB remains external. Memty remains a separate local CLI vault. Create the environment files as above, set a reachable `MONGO_URI` and stable `SESSION_SECRET` in `backend/.env`, and replace the example `MEMORY_VAULT_API_TOKEN` with a random secret of at least 32 characters in `.env`.

```powershell
docker compose up --build
```

The legacy Vault API stays on Compose's private network. Open [http://localhost:3001](http://localhost:3001); stop the stack with `Ctrl+C` or `docker compose down`. Compose does not migrate existing MongoDB memories into Memty.

<a id="project-map"></a>
## 🗺️ Project map

| Path | What lives here | Start here |
| --- | --- | --- |
| [`app/`](app/README.md) | Next.js pages, API routes, chat orchestration, and UI styles | [`app/api/chat/route.ts`](app/api/chat/route.ts) |
| [`backend/`](backend/README.md) | Express routes, authentication, MongoDB models, and memory services | [`backend/server.js`](backend/server.js) |
| [`providers/`](providers/README.md) | Model registry, provider adapters, and fallbacks | [`providers/index.js`](providers/index.js) |
| [`memty/`](memty/README.md) | CLI-first atomic memory vault, SQLite ledger, context compiler, tests, and optional MCP server | [`memty/cli.py`](memty/cli.py) |
| [`memoryport/`](memoryport/README.md) | Legacy Python SDK, model router, temporal ledger, and compatibility integrations | [`memoryport/sdk.py`](memoryport/sdk.py) |
| [`nexorai/`](nexorai/__init__.py) | Short public Python import path for the SDK | [`nexorai/__init__.py`](nexorai/__init__.py) |
| [`components/`](components/legacy-page.tsx) · [`lib/`](lib/legacy-markup.ts) · [`public/`](public/) | Shared wrapper, legacy page markup, and browser assets/scripts | [`components/legacy-page.tsx`](components/legacy-page.tsx) |
| [`templates/`](templates/) · [`static/`](static/) | Legacy HTML templates and static assets | — |
| [`assets/`](assets/) | Project and provider artwork used by the UI and documentation | — |
| [`compose.yaml`](compose.yaml) · [`Dockerfile`](Dockerfile) · [`Dockerfile.vault`](Dockerfile.vault) | Local multi-service deployment and container builds | [Compose setup](#start-with-docker-compose) |
| [`.env.example`](.env.example) · [`backend/.env.example`](backend/.env.example) | Frontend/provider and backend configuration templates | [Configuration](#configuration-at-a-glance) |

<a id="choose-your-path"></a>
### Choose your path

- **Frontend contributor:** [routes, UI, and responsive styles](app/README.md)
- **API or data contributor:** [backend routes, sessions, and MongoDB](backend/README.md)
- **Model contributor:** [provider adapters and fallbacks](providers/README.md)
- **Memory contributor:** [Memty CLI and atomic vault](memty/README.md)
- **Legacy SDK contributor:** [MemoryPort compatibility package](memoryport/README.md)
- **Memory feature reader:** [memory lifecycle and storage guide](app/memory/README.md)

<a id="configuration-at-a-glance"></a>
## ⚙️ Configuration at a glance

The root `.env` configures Next.js and model providers. `backend/.env` configures MongoDB and the Express service; the backend loads the root environment first, then lets backend values override it.

| Setting | Service | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY`, `CLAUDE_API_KEY`, `GROK_API_KEY`, `KIMI_API_KEY` | Frontend and/or backend | Enable the corresponding model features. |
| `OPEN_ROUTER_OPEN_API_KEYS`, `OPEN_ROUTER_API_KEY` | Frontend | Enable OpenRouter-backed models. |
| `MONGO_URI`, `MONGO_DATABASE`, `MEMORY_DATABASE` | Backend | Connect to account and memory databases. |
| `SESSION_SECRET` | Backend | Sign account sessions; use a stable high-entropy value in production. |
| `PROXY_TARGET` | Frontend | Backend URL; defaults to `http://localhost:3002`. |
| `MEMORY_VAULT_API_URL`, `MEMORY_VAULT_API_TOKEN` | Backend and Vault | Connect the trusted backend to the optional Vault API. |

See [`.env.example`](.env.example) and [`backend/.env.example`](backend/.env.example) for all options. Never commit real credentials or paste them into issues.

For semantic memory retrieval, create the Atlas Search vector index on `Memory.user_memories` using [`backend/memory-vector-index.json`](backend/memory-vector-index.json). The configured index expects 768-dimensional cosine vectors and filters for `userId` and `status`. Without the index or an embedding service, retrieval can use lexical and recency scoring.

<a id="current-limitations"></a>
## ⚠️ Current limitations

- Chat responses are not streamed.
- The frontend request limit is in-memory per frontend process, not a shared account quota.
- Public launch needs an account deletion and retention process, shared abuse controls, monitoring, backups, and deployment-specific security review.
- Model availability, IDs, prices, and provider behavior depend on external providers and your configuration.
- Cost figures are estimates only when operators configure per-model rates; they are not billing records.
- Memty's working SQLite database is plaintext on disk. Week 1 does not provide encryption or remote synchronization.

Review the [Privacy Notice](app/privacy/page.tsx) and [Terms](app/terms/page.tsx) against your deployment and applicable provider agreements before release.

## 📚 More documentation

- [Frontend and mobile layout](app/README.md)
- [Backend, routes, and MongoDB](backend/README.md)
- [Memory layers, retrieval, and storage](app/memory/README.md)
- [Provider adapters and costs](providers/README.md)
- [Memty CLI and atomic vault](memty/README.md)
- [Legacy Python MemoryPort SDK](memoryport/README.md)
- [Frontend scripts](package.json) · [Backend scripts](backend/package.json) · [Python package configuration](pyproject.toml)

## 🤝 Contributing

Start with the [contributor guide](CONTRIBUTING.md), choose the guide for the area you are changing, and pick a focused issue. Keep credentials and personal data out of commits and issue attachments.
