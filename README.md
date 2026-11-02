<div align="center">

<img src="assets/memty_logo.png" alt="Memty logo" width="180" />

# Memty

### One workspace for multiple AI models, conversations, and portable memory.

[Explore the code](#project-map) · [Run locally](#get-started) · [Understand the architecture](#how-it-fits-together) · [Find a guide](#choose-your-path)

</div>

Memty is a multi-provider AI workspace and portable-memory toolkit built with **Next.js**, an **Express** account service, **MongoDB**, and a local Python SDK. One `memty` package provides the model-routing SDK, atomic memory vault, CLI, and optional HTTP and MCP integrations. The web workspace keeps signed-in account data in MongoDB; the local SDK and CLI keep their vault data on the user's device.

This project is licensed under the [MIT License](LICENSE).

> **Project status:** provider access depends on your own credentials. Some production features are still planned; see [current limitations](#current-limitations) before deploying publicly.

## ✨ What you can do

| Chat across providers | Own memory from the CLI | Keep useful context |
| --- | --- | --- |
| Select a configured model, use fallbacks, or compare responses. | Store, inspect, recall, constrain, and delete facts with the `memty` command. | Compile deterministic, provider-filtered context without sending the whole vault to an assistant. |

The workspace also includes a responsive chat UI, model availability metadata, a memory dashboard, privacy and terms pages, and a first-party API reference. The atomic vault is standard-library-only: it stores facts, logical constraints, rolling summaries, and raw drill-down records in `~/.memty/ledger.sqlite3`. Smart model routing and multi-provider chat are available from the same Python package.

<a id="how-it-fits-together"></a>
## 🧭 How it fits together

![Memty system architecture: browser, Next.js, model providers, Express API, MongoDB, and optional local memory services](docs/architecture.svg)

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

Once the first PyPI release is published, users can install the distribution with `python -m pip install memty`. Until then, an account with repository access can install the renamed GitHub repository directly:

```powershell
python -m pip install "memty @ git+https://github.com/RohanNK86/memty.git@main"
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

### Use Memty's model SDK

The same install provides prompt-aware routing, provider adapters, and a local chat client:

```powershell
memty init
# Edit ~/.memty/models.json and set each configured provider's API key in your environment.
memty models
memty route "Review this Python function"
memty chat --interactive --chat-id work
```

```python
from memty import Memty, ModelConfig, load_client

client = load_client()  # reads ~/.memty/models.json
answer = client.chat("Review this Python function", chat_id="code-review")
print(answer.model_id, answer.text)
```

The SDK's historical temporal ledger remains available during migration; its existing data files are reused when found. The atomic CLI vault and web account memory keep their established storage and access boundaries.

### Start with Docker Compose

Compose starts the frontend, backend, and optional Memty HTTP vault service. MongoDB remains external. The Memty CLI can also use its local SQLite vault independently. Create the environment files as above, set a reachable `MONGO_URI` and stable `SESSION_SECRET` in `backend/.env`, and replace the example `MEMORY_VAULT_API_TOKEN` with a random secret of at least 32 characters in `.env`.

```powershell
docker compose up --build
```

The Memty HTTP vault stays on Compose's private network. Open [http://localhost:3001](http://localhost:3001); stop the stack with `Ctrl+C` or `docker compose down`. Compose does not migrate existing MongoDB memories into the local Memty vault.

<a id="project-map"></a>
## 🗺️ Project map

| Path | What lives here | Start here |
| --- | --- | --- |
| [`app/`](app/README.md) | Next.js pages, API routes, chat orchestration, and UI styles | [`app/api/chat/route.ts`](app/api/chat/route.ts) |
| [`backend/`](backend/README.md) | Express routes, authentication, MongoDB models, and memory services | [`backend/server.js`](backend/server.js) |
| [`providers/`](providers/README.md) | Model registry, provider adapters, and fallbacks | [`providers/index.js`](providers/index.js) |
| [`memty/`](memty/README.md) | Public Python API, smart-routing SDK, CLI, atomic vault, context compiler, and MCP entry points | [`memty/__init__.py`](memty/__init__.py) |
| [`memoryport/`](memoryport/README.md) | Internal compatibility implementations retained for existing vaults and integrations | [`memoryport/README.md`](memoryport/README.md) |
| [`GitPage/`](GitPage/index.html) | Memty product site, quick starts, architecture, and integration guides | [`GitPage/index.html`](GitPage/index.html) |
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
- **Python SDK contributor:** [Memty SDK and vault guide](memty/README.md)
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
- [Memty Python SDK and CLI](memty/README.md)
- [Frontend scripts](package.json) · [Backend scripts](backend/package.json) · [Python package configuration](pyproject.toml)

## 🤝 Contributing

Start with the [contributor guide](CONTRIBUTING.md), choose the guide for the area you are changing, and pick a focused issue. Keep credentials and personal data out of commits and issue attachments.
