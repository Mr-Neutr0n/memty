# NexorAI Smart Auto

This Python package provides a local model router and a portable memory vault. The vault adds a deterministic, bi-temporal fact ledger, provider policy filtering, a compact context compiler, an encrypted `.nxvault` bundle, an HTTP API, and an optional approval-only MCP server. The core can use local SQLite or a dedicated MongoDB `memory_vault_ledger` collection; it makes no model calls. The older `PortableMemoryStore` and optional MongoDB mirror remain available for compatibility. NexorAI's Node backend can connect chat recall and dashboard fact operations to the vault through its authenticated internal API; conversation summaries and usage stay in MongoDB.

## Memory Vault quick start

The base ledger has no third-party dependencies and stores data at any path you choose:

```python
from SmartMemory import MemoryLedger

vault = MemoryLedger(".nexor/memory.sqlite3", user_id="local")
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

The CLI prompts for the passphrase instead of putting it in shell history. The archive contains a manifest, ledger history, provider policies, and hashes. Encrypted bundles use AES-256-GCM with a scrypt-derived key; this first version does not add an Ed25519 user signature or precomputed embeddings.

## Local MCP and HTTP interfaces

The MCP server is stdio-only and is intended to be launched as a child process by a local AI client. It exposes `read_context`, `propose_fact`, and `list_my_pending_proposals`. Agent writes remain pending until the user approves them with `nexor-vault approve <proposal_id>`; an MCP agent cannot approve its own proposal. Set `NEXOR_VAULT_PATH`, `NEXOR_VAULT_USER`, and optionally `NEXOR_VAULT_PROVIDER` in the MCP client's server configuration.

```powershell
pip install -e ".[mcp,crypto]"
```

The optional HTTP API is for a local UI or trusted backend bridge. It defaults to loopback and requires a bearer token of at least 32 characters. A non-loopback bind requires the explicit `NEXOR_VAULT_ALLOW_REMOTE=true` setting and should only be used on a private network with the API port unpublished. It exposes ledger, context, proposal, approval, and encrypted-export endpoints:

```powershell
pip install -e ".[server,crypto]"
$env:NEXOR_VAULT_API_TOKEN = "use-a-random-secret-of-at-least-32-characters"
python -m SmartMemory.api
```

To use the new MongoDB collection, install the Mongo extra and set `NEXOR_VAULT_BACKEND=mongodb`, `NEXOR_VAULT_MULTIUSER=true`, `MONGO_URI`, and `MEMORY_DATABASE=Memory`. The API then requires the authenticated backend to send its user ID in `X-Nexor-User`; user data is stored under that ID in `memory_vault_ledger`. This backend requires a MongoDB replica set because state changes use transactions. Example local service setup:

```powershell
pip install -e ".[mongodb,server,crypto]"
$env:NEXOR_VAULT_BACKEND = "mongodb"
$env:NEXOR_VAULT_MULTIUSER = "true"
$env:MONGO_URI = "<your MongoDB URI>"
$env:MEMORY_DATABASE = "Memory"
$env:NEXOR_VAULT_API_TOKEN = "<a random secret of at least 32 characters>"
python -m SmartMemory.api
```

For the NexorAI chat/dashboard bridge, set `MEMORY_VAULT_API_URL=http://127.0.0.1:8765` and `MEMORY_VAULT_API_TOKEN` in `backend/.env`; set the same token as `NEXOR_VAULT_API_TOKEN` in the Python process. Keep `NEXOR_VAULT_MULTIUSER=true` so each authenticated account ID gets an isolated vault. In Docker Compose, the backend uses the private address `http://memory-vault:8765`; Compose sets the required non-loopback opt-in and does not publish that API port. The Node backend routes memory recall, validated fact extraction, and dashboard fact CRUD through Python. Existing conversation summaries and usage remain in MongoDB.

Use `nexor-vault evaluate cases.json` to calculate stale-fact bleed rate, deleted-slot stickiness, and distinct injected facts per approximate 100 tokens. The JSON file is a list of cases with fields such as `query`, `provider`, and `stale_values`; deleted-slot cases also specify `deleted_slot`, `namespace`, `slot_key`, and `deleted_value`. This measures the deterministic vault's own behavior; it is not yet a comparative Cognee/Graph-RAG benchmark.

MCP v2 currently requires Python 3.11 or newer. The core ledger itself remains compatible with Python 3.10+.

## Current integration boundary

The NexorAI Node backend can call the Python API for chat recall, fact extraction, and memory dashboard CRUD when both `MEMORY_VAULT_API_URL` and `MEMORY_VAULT_API_TOKEN` are set. Compose includes the Python service; local development can start it separately. When those settings are absent, NexorAI uses its existing MongoDB fact-memory path. Conversation transcripts, episode summaries, and usage counts remain in MongoDB. Browser IndexedDB/CRDT synchronization, clickable source-message navigation, and signed user identities remain future work.

## Quick start

```python
from SmartMemory import ModelSpec, SmartRouter

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
score(a)  = UCB(a, x) - λ·normalized_cost(a) + 0.3·capability(a)·S
```

`Aₐ` and `bₐ` are updated after feedback, with `θₐ = Aₐ⁻¹bₐ`; `α` controls exploration and `λ` is `cost_weight`. The router chooses the eligible model with the highest score. Cost is normalized from the configured input-plus-output rates, so it is a relative proxy, not an exact per-request bill. In production, tune these weights and validate quality and actual spend on representative traffic before relying on the learned preference.

## Portable memory

```python
from SmartMemory import PortableMemoryStore

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
from SmartMemory import MongoSyncedMemoryStore

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
