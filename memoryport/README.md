# MemoryPort for NexorAI

MemoryPort is NexorAI's portable Python memory vault and model SDK. It combines prompt-aware model routing with a per-user temporal fact ledger, local vector embeddings, provider-aware retrieval, portable encrypted exports, an HTTP API, and optional MCP integration. The default SDK install uses SQLite on the device and has no required third-party dependencies. Embedding and chat providers are configurable; local Ollama embeddings are the starter default.

## NexorAI Python SDK

The package includes the router, the portable MemoryPort vault, and a local-first chat client. It can rank models with task rules, cost/latency metadata, or adaptive LinUCB feedback, then call the selected provider through a standard-library HTTP client. `load_client()` opens the same local vault for every chat and model by default, so changing assistants does not discard saved facts. Chat transcripts remain in memory; the fact ledger is durable on the device.

```python
from nexorai import ModelConfig, NexorAI

client = NexorAI([
    ModelConfig(
        id="cloud-coder",
        provider="openai-compatible",
        model="your-provider-model-id",
        base_url="https://your-openai-compatible-endpoint/v1",
        api_key_env="MY_PROVIDER_KEY",  # set this environment variable separately
        capability=0.82,                 # operator estimate from your own evaluation
        context_tokens=64_000,
        tags=("code", "general"),
    ),
    ModelConfig(
        id="local-coder",
        provider="ollama",
        model="your-local-model-name",
        capability=0.70,
        context_tokens=16_000,
        tags=("code", "local"),
    ),
], routing="adaptive")

# Each chat ID has its own transcript and can pin a different model.
answer = client.chat("Review this Python function", chat_id="code-review")
client.select_model("local-coder", chat_id="private-notes")
private_answer = client.chat("Summarize these notes", chat_id="private-notes")

# Train adaptive routing from an observed outcome, never from guessed quality.
client.feedback("code-review", outcome="accepted")
print(answer.model_id, answer.text)
```

Supported built-in adapters are OpenAI-compatible endpoints (including OpenRouter, Ollama, and LM Studio), Anthropic Messages, and the Gemini Interactions API. Add a custom adapter by implementing `complete(model, messages, system=...)` and passing it as `adapters={"provider-name": adapter}`. Set capability, context length, initial latency, and prices from your own evaluation; the SDK does not scrape provider catalogs or claim a universal model ranking. It blends observed response latency into routing for the current process. Provider-reported usage is returned when available, and cost is estimated only from the rates you enter.

`load_client()` uses `~/.nexorai/memory.sqlite3` and the local account ID `local` unless `NEXORAI_MEMORY_PATH` and `NEXORAI_MEMORY_USER` are set. If that new path is empty but the older `~/.nexor/memory.sqlite3` exists, it reuses the old vault in place. All chats share that account's vault. `client.remember(...)` saves a user-confirmed fact; `client.recall(...)` and every `client.chat(...)` retrieve provider-filtered context. Use the `nexor-vault` CLI to review, edit, export, or delete the same facts. This is shared across chats and model changes on this device; it does not sync between devices unless you configure a remote ledger.

The starter catalog configures a local Ollama embedding model (`nomic-embed-text`). Install/pull that model in Ollama to get local vector search; if it is unavailable, the SDK falls back to lexical retrieval. Embeddings are saved in the same SQLite vault and stay compatible across chat models because the embedding model is configured independently. For cloud embeddings, set the `memory.embedding` provider, model, and API key environment variable in `models.json`; your queries and eligible facts will then be sent to that embedding provider. Secret facts are never embedded, and INTERNAL/CONFIDENTIAL facts only go to a local embedder or one explicitly allowed in the fact policy.

```shell
ollama pull nomic-embed-text
```

Automatic extraction is enabled in the starter catalog and controlled by `memory.auto_extract` in `~/.nexorai/models.json`; set it to `false` to disable it. The SDK uses the selected answer model for extraction, then checks that each saved fact has an exact quote in the user's prompt, rejects secret-like content, and requires confidence of at least 0.8. Extraction adds a provider request and may incur cost; the chat reply still succeeds if extraction fails. Saved facts are marked as automatically extracted and can be reviewed or removed through `nexor-vault`.

For example, load the shared local vault from any Python assistant and explicitly save or recall a fact:

```python
from nexorai import load_client

assistant = load_client()  # reads ~/.nexorai/models.json and the shared local vault
assistant.remember("work.preferences", "editor", "VS Code")
reply = assistant.chat("Which editor do I use?", chat_id="support-chat")
print(reply.text, reply.memories_saved)
print(assistant.recall("my preferred editor")["text"])
```

The starter config enables automatic extraction. Keep or remove that setting to control it:

```json
{
  "memory": {
    "auto_extract": true,
    "embedding": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "base_url": "http://localhost:11434/v1"
    }
  }
}
```

To generate a local starter catalog, install the package and run `nexorai init`. Edit `~/.nexorai/models.json`, set the named API key environment variables in your shell, then use:

```shell
nexorai models
nexorai route "Explain this repository's architecture"
nexorai chat --interactive --chat-id work
```

Choose `routing="rules"`, `"cheapest"`, `"fastest"`, or `"adaptive"`. Use `select_model(model_id, chat_id=...)` to keep one model for a particular chat, or leave each chat on Auto. `NEXORAI_STATE_PATH` controls where numeric adaptive feedback is saved. Prompts and chat transcripts are not written to disk by the SDK; observed latency is held in memory and starts from the catalog estimate again in a new process.

### Connect coding agents through MCP

The optional `nexorai-mcp` server exposes `recommend_model` (local recommendation only), `delegate_prompt` (a separate request to your selected provider), `search_memory`, `remember_fact`, `rate_last_response`, and `list_configured_models`. Each client uses the same local MemoryPort vault, so facts saved from one coding assistant can be recalled by another. Pass `delegate_prompt` a unique stable `chat_id` for each host conversation so separate agent sessions do not share prompt history. The server only sees host conversation content that the agent explicitly sends through a tool call; it does not read or import host transcripts automatically. It works with MCP-capable Codex, Claude Code, and VS Code Copilot clients:

```shell
nexorai integration codex
nexorai integration claude-code
nexorai integration vscode
```

Install the `mcp` extra first (Python 3.11 or later). `nexorai integration ...` only prints setup instructions; it does not rewrite your agent settings. Run the Codex or Claude Code command it prints to register the local server. For VS Code, put its JSON snippet in `.vscode/mcp.json` under the top-level `servers` property, then restart the client. MCP lets an agent request a model recommendation or delegate a subtask; it does not change the model hosting the agent's current conversation or use that host's subscription credentials. Delegated prompts and chat history go to the API provider you configured, subject to that provider's data handling and account.

The supported setup formats are documented by [Codex MCP](https://developers.openai.com/codex/mcp/), [Claude Code MCP](https://code.claude.com/docs/en/mcp), and [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration). 

[← NexorAI overview](../README.md) · [Backend integration](../backend/README.md) · [Memory lifecycle](../app/memory/README.md)

## Pick the right entry point

| Goal | Start here |
| --- | --- |
| Use a local fact vault from the command line | [Install and CLI quick start](#one-command-local-install) |
| Embed memory in a Python application | [Memory Vault quick start](#memory-vault-quick-start) |
| Choose a model using task features and feedback | [SmartRouter quick start](#quick-start) |
| Connect the local HTTP API to a trusted service | [HTTP interface](#local-mcp-and-http-interfaces) |
| Understand where the Python service fits in NexorAI | [Current integration boundary](#current-integration-boundary) |

```text
Your app / NexorAI backend
          │ trusted API or Python library
          ▼
    MemoryPort vault ─── SQLite ledger or MongoDB ledger
          │
          ├── provider-filtered context
          ├── user-approved fact proposals
          └── encrypted .nxvault export
```

## One-command local install

The installers create an isolated Python environment under the user's local NexorAI data folder, then install this package from GitHub. Python 3.10+ and Git must already be installed. Review the script before running it if you want to inspect what it does.

**Access note:** This GitHub repository is currently private. These installers and the pip-from-GitHub commands below work only for GitHub users who have repository read access and Git credentials configured. To offer one-command installs to everyone, make the source repository public or publish the package to PyPI.

**Windows (PowerShell):**

```powershell
$installer = Join-Path $env:TEMP "install-memoryport.ps1"
Invoke-WebRequest "https://raw.githubusercontent.com/RohanNK86/Open_AI_Bot/main/scripts/install-memoryport.ps1" -OutFile $installer
& $installer
```

For encrypted exports, add `-Extras "crypto"`. Extras can be combined, such as `-Extras "mongodb,server,crypto"`; MCP requires Python 3.11+.

**macOS / Linux (bash):**

```bash
curl -fsSLo install-memoryport.sh https://raw.githubusercontent.com/RohanNK86/Open_AI_Bot/main/scripts/install-memoryport.sh
bash install-memoryport.sh
```

Pass extras as the first argument, for example `bash install-memoryport.sh crypto` or `bash install-memoryport.sh mongodb,server,crypto`.

The default CLI locations are `%LOCALAPPDATA%\NexorAI\memoryport\venv\Scripts\nexor-vault.exe` on Windows and `~/.local/share/nexorai/venv/bin/nexor-vault` on macOS/Linux. Example commands:

```powershell
& "$env:LOCALAPPDATA\NexorAI\memoryport\venv\Scripts\nexor-vault.exe" add demo.preferences editor "VS Code"
& "$env:LOCALAPPDATA\NexorAI\memoryport\venv\Scripts\nexor-vault.exe" context local "Which editor do I use?"
```

```bash
~/.local/share/nexorai/venv/bin/nexor-vault add demo.preferences editor "VS Code"
~/.local/share/nexorai/venv/bin/nexor-vault context local "Which editor do I use?"
```

The router is a Python library, not a model host: your application supplies its model list and sends the selected prompt to its own provider adapter. See the SmartRouter example below.

## Manual install

The package is named `nexorai-smart-auto` and includes both MemoryPort and SmartRouter. Until a release is published to PyPI, install directly from GitHub. This requires Python 3.10 or newer, Git on your PATH, and read access to this private repository.

**macOS / Linux (bash):**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "nexorai-smart-auto @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install "nexorai-smart-auto @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"
```

Install optional features only when you need them:

```bash
# Encrypted .nxvault export/import
python -m pip install "nexorai-smart-auto[crypto] @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"

# MongoDB backend, local HTTP API, and encryption
python -m pip install "nexorai-smart-auto[mongodb,server,crypto] @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"

# MCP server (Python 3.11+)
python -m pip install "nexorai-smart-auto[mcp,crypto] @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"
```

On Windows, run those optional install commands with `py -m pip` (or the virtual environment's `.venv\\Scripts\\python -m pip`). See the [pip VCS install guide](https://pip.pypa.io/en/stable/topics/vcs-support/) for installing a package from Git.

After installation, confirm the CLI is available with `nexor-vault --help`. The base vault and router need no provider keys or third-party dependencies; callers connect their own model SDKs and credentials.

Create a local fact and retrieve provider-filtered context:

```shell
nexor-vault add demo.preferences editor "VS Code"
nexor-vault list
nexor-vault context local "Which editor do I use?"
```

The CLI and Python SDK use `~/.nexorai/memory.sqlite3` by default. Use `nexor-vault --db ./memory.sqlite3 ...` or set `NEXORAI_MEMORY_PATH` to choose another location. SmartRouter is used from Python; its quick start is below.

## Memory Vault quick start

The base ledger has no third-party dependencies and stores data at any path you choose:

```python
from memoryport import MemoryLedger

vault = MemoryLedger(".nexorai/memory.sqlite3", user_id="local")
vault.record(
    "work.nexor_ai.architecture", "primary_database", "MongoDB Atlas",
    verification_state="USER_CONFIRMED", source_conversation_id="conv_123",
    source_message="We use MongoDB Atlas for the account memory store.",
)

context = vault.context("Which database does NexorAI use?", provider="claude", token_budget=900)
print(context["text"])
print(context["citations"])
```

The `nexor-vault` command also supports `add`, `list`, `context`, `delete`, `proposals`, `approve`, `reject`, `export`, `import`, and `evaluate` operations.

Each change appends a version with a canonical namespace/slot, valid-time bounds, recorded time, confidence, source-message SHA-256, verification state, and provider policy. Replacing an active slot supersedes its old value instead of mixing contradictory versions. `vault.as_of(namespace, slot_key, when, known_at=...)` supports valid-time and recorded-time lookups. `vault.delete(id)` removes that memory's stored text/history and leaves a slot tombstone so automatic extraction cannot silently restore it; an explicit user-confirmed write can restore the slot. Deletion is the intentional exception to append-only history: privacy erasure purges the deleted fact's prior plaintext versions.

For first-party chat integrations, `MemoryExtractor` accepts a caller-provided model function, verifies that each extracted fact has a source quote in the user's message, rejects low-confidence or secret-like candidates, and writes approved-confidence facts into canonical slots. The HTTP API also exposes `POST /v1/extract` for a trusted backend that already produced structured candidates. The vault does not choose or call an LLM itself.

The compiler filters by provider before retrieval. `SECRET` memories are available only to the configured local provider names (`local`, `ollama`, `local_ollama`, `nexor_local`). `INTERNAL` and `CONFIDENTIAL` facts require an explicit provider allow-list before an external provider can receive them. `ephemeral_redaction=True` replaces the value with a placeholder; the placeholder-to-value map is returned only to a trusted in-process caller and is deliberately removed by the MCP tool. Token counts use a documented rough estimate of four characters per token, not a model tokenizer.

The working SQLite database is currently plaintext on disk and should be kept in a user-protected directory. Encryption applies to exported `.nxvault` bundles; at-rest database encryption is not included in this version.

## Portable `.nxvault` files

Install the encryption extra, then export. AES-GCM encryption is the default; plaintext requires an explicit opt-in:

```powershell
pip install -e ".[crypto]"
nexor-vault export .\backup.nxvault
nexor-vault import .\backup.nxvault
```

The CLI prompts for the passphrase instead of putting it in shell history. The archive contains a manifest, ledger history, provider policies, and hashes. Encrypted bundles use AES-256-GCM with a scrypt-derived key. Embedding vectors stay in the local SQLite vault and are not included in the portable bundle; the destination can regenerate them with its configured embedding model.

## Local MCP and HTTP interfaces

The MCP server is stdio-only and is intended to be launched as a child process by a local AI client. It exposes `read_context`, `propose_fact`, and `list_my_pending_proposals`. Agent writes remain pending until the user approves them with `nexor-vault approve <proposal_id>`; an MCP agent cannot approve its own proposal. Set `NEXOR_VAULT_PATH`, `NEXOR_VAULT_USER`, and optionally `NEXOR_VAULT_PROVIDER` in the MCP client's server configuration.

```powershell
pip install -e ".[mcp,crypto]"
```

The optional HTTP API is for a local UI or trusted backend bridge. It defaults to loopback and requires a bearer token of at least 32 characters. A non-loopback bind requires the explicit `NEXOR_VAULT_ALLOW_REMOTE=true` setting and should only be used on a private network with the API port unpublished. It exposes ledger, context, proposal, approval, and encrypted-export endpoints:

```powershell
pip install -e ".[server,crypto]"
$env:NEXOR_VAULT_API_TOKEN = "use-a-random-secret-of-at-least-32-characters"
python -m memoryport.api
```

To use the new MongoDB collection, install the Mongo extra and set `NEXOR_VAULT_BACKEND=mongodb`, `NEXOR_VAULT_MULTIUSER=true`, `MONGO_URI`, and `MEMORY_DATABASE=Memory`. The API then requires the authenticated backend to send its user ID in `X-Nexor-User`; user data is stored under that ID in `memory_vault_ledger`. This backend requires a MongoDB replica set because state changes use transactions. Example local service setup:

```powershell
pip install -e ".[mongodb,server,crypto]"
$env:NEXOR_VAULT_BACKEND = "mongodb"
$env:NEXOR_VAULT_MULTIUSER = "true"
$env:MONGO_URI = "<your MongoDB URI>"
$env:MEMORY_DATABASE = "Memory"
$env:NEXOR_VAULT_API_TOKEN = "<a random secret of at least 32 characters>"
python -m memoryport.api
```

For the NexorAI chat/dashboard bridge, set `MEMORY_VAULT_API_URL=http://127.0.0.1:8765` and `MEMORY_VAULT_API_TOKEN` in `backend/.env`; set the same token as `NEXOR_VAULT_API_TOKEN` in the Python process. Keep `NEXOR_VAULT_MULTIUSER=true` so each authenticated account ID gets an isolated vault. In Docker Compose, the backend uses the private address `http://memory-vault:8765`; Compose sets the required non-loopback opt-in and does not publish that API port. The Node backend routes memory recall, validated fact extraction, and dashboard fact CRUD through Python. Existing conversation summaries and usage remain in MongoDB.

Use `nexor-vault evaluate cases.json` to calculate stale-fact bleed rate, deleted-slot stickiness, and distinct injected facts per approximate 100 tokens. The JSON file is a list of cases with fields such as `query`, `provider`, and `stale_values`; deleted-slot cases also specify `deleted_slot`, `namespace`, `slot_key`, and `deleted_value`. This measures the deterministic vault's own behavior; it is not yet a comparative Cognee/Graph-RAG benchmark.

MCP v2 currently requires Python 3.11 or newer. The core ledger itself remains compatible with Python 3.10+.

## Current integration boundary

The NexorAI Node backend can call the Python API for chat recall, fact extraction, and memory dashboard CRUD when both `MEMORY_VAULT_API_URL` and `MEMORY_VAULT_API_TOKEN` are set. Compose includes the Python service; local development can start it separately. When those settings are absent, NexorAI uses its existing MongoDB fact-memory path. Conversation transcripts, episode summaries, and usage counts remain in MongoDB. Browser IndexedDB/CRDT synchronization, clickable source-message navigation, and signed user identities remain future work.

## Quick start

```python
from memoryport import ModelSpec, SmartRouter

router = SmartRouter([
    ModelSpec("gemini-flash", "Google", 0.10, 0.40, 0.55, 1_000_000),
    ModelSpec("claude-haiku", "Anthropic", 0.80, 4.00, 0.75, 200_000),
    ModelSpec("kimi", "Moonshot", 0.60, 2.50, 0.85, 128_000),
], state_path=".smart_auto/bandit.json")

decision = router.route(
    "Summarize the key points from our previous project discussion",
    memory_relevance=0.84,
    memory_coverage=0.65,
)
print(decision.model_id, decision.reason)

# Call your provider adapter with decision.model_id, then record feedback.
reward = router.reward_from_signals(accepted=True)
router.update(decision.model_id, "Summarize the key points from our previous project discussion",
              reward, memory_relevance=0.84, memory_coverage=0.65)
```

Model capabilities and rates are operator supplied: provider pricing and model IDs change. Set `available=False` for a provider without credentials. The router only selects among available models and respects context and capability limits. It applies memory discount only to prompts that appear to use prior context. LinUCB state is saved locally; it contains numeric learning state, not prompts or memory text.

## Routing math intuition

The router builds an eight-value context vector `x` from a bias term, prompt length, code signals, reasoning signals, long-context and structured-output signals, memory relevance, and memory coverage. Each signal is normalized to `[0, 1]`.

First it estimates prompt complexity:

```text
C = clip(0.08 + 0.28·length + 0.16·code + 0.34·reasoning
         + 0.14·long_context + 0.05·structured, 0, 1)
S = clip(C - γ·relevance·coverage, 0, 1)   # only for memory-referencing prompts
```

Here `γ` is the configurable `memory_discount` (default `0.25`). `S` is the effective complexity score. Models whose configured capability is below `S`, or whose context window is too small, are excluded. This is a routing heuristic, not a measured probability of success; the capability values need to be calibrated against your own tasks.

For each eligible model `a`, LinUCB estimates outcome utility and uncertainty from feedback:

```text
UCB(a, x) = θₐᵀx + α·√(xᵀAₐ⁻¹x)
score(a)  = UCB(a, x) - λ·normalized_cost(a) - μ·normalized_latency(a) + 0.3·capability(a)·S
```

`Aₐ` and `bₐ` are updated after feedback, with `θₐ = Aₐ⁻¹bₐ`; `α` controls exploration, `λ` is `cost_weight`, and `μ` is `latency_weight`. Latency estimates come from the caller's model catalog; unknown latency is treated neutrally. Cost and latency are normalized relative to the eligible models, so both are ranking signals rather than exact measurements. In production, calibrate model capability and latency, tune these weights, and validate quality and actual spend on representative traffic before relying on the learned preference.

## Portable memory

```python
from memoryport import PortableMemoryStore

memory = PortableMemoryStore(".smart_auto/memories.json")
memory.add("The project uses Next.js and MongoDB", kind="semantic", importance=0.8)
matches = memory.retrieve("What database does the project use?")
backup = memory.export()                 # JSON-compatible portable document
memory.import_data(backup, replace=False) # deduplicates by fact text
```

The format is `nexor-portable-memory-v1`. Entries can optionally carry caller-generated embeddings, allowing cosine ranking without binding this package to an embedding vendor. Without vectors it uses lightweight lexical ranking. The JSON file is local and should be protected like other user data.

### Keep the existing MongoDB memory in sync

Install the optional driver with `pip install -e ".[mongodb]"`, then create a store using the authenticated user's MongoDB ObjectId:

```python
import os
from memoryport import MongoSyncedMemoryStore

memory = MongoSyncedMemoryStore(
    uri=os.environ["MONGO_URI"],
    user_id=authenticated_user_id,  # Obtain from the signed-in session; never trust a client-supplied ID.
    path=".smart_auto/memories.json",
    database=os.getenv("MEMORY_DATABASE", "Memory"),
)
try:
    matches = memory.retrieve("What are my project preferences?")
    memory.add("The project prefers concise technical answers", kind="style")
finally:
    memory.close()
```

Each read refreshes the local JSON mirror from that user's `user_memories` documents. Python additions and imports write to MongoDB first and then refresh the mirror. The adapter is user-scoped, leaves the Next.js MongoDB schema intact, and imports additively; use the existing memory dashboard for deletion. The Python app must use the same MongoDB URI and database as the backend. Changes made by the Next.js app appear in the mirror on the next Python store operation.

## Feedback mapping

Use `reward_from_signals` with observed outcomes: accepted or within-budget responses receive `+1`, a provider fallback receives `-1`, and regenerate/correction receives `-2`. Do not treat mere conversation continuation as proof of answer quality. Update the same model and feature context used for the route. Learning improves with observations and is not a quality guarantee; begin with explicit model capability constraints and review actual quality and spend before changing production policy.

This package intentionally does not implement speculative logprob cancellation: support varies by provider, and the existing NexorAI adapters are non-streaming. Similarity scores from vector databases are inputs that must be calibrated for their particular index; the router does not assume an Atlas score is a raw cosine similarity.

