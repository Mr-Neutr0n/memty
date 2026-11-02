# Portable memory guide

Memty stores user memory in its own MongoDB database so selected model providers can share relevant context. Memory is scoped to the signed-in account. Users can inspect and manage saved facts from `/memory`.

> **Reader's map:** this guide explains what is stored and how it is retrieved. For the dashboard UI, see [`page.tsx`](page.tsx) and [`memory-dashboard.tsx`](memory-dashboard.tsx). For endpoints and database models, see the [backend guide](../../backend/README.md). For the optional Python ledger, see [Memty](../../memty/README.md).

```text
Signed-in chat → backend retrieves scoped context → provider receives a compact brief
       │                                            │
       └── completed turn is saved in MongoDB       └── user manages facts at /memory
```

## Memory layers

- **Working context:** recent messages in the active neutral-format conversation and a rolling summary when context grows.
- **Episodic memory:** short summaries of saved conversations for continuity in later chats.
- **Semantic memory:** durable user facts such as projects, tools, goals, and preferences.
- **Style memory:** response preferences such as concise answers or code-first explanations.

The automatic memory writer is optional and uses the configured Gemini model when `GEMINI_API_KEY` is available. It proposes JSON facts with a type, confidence, importance, and source text. The service deduplicates candidates and archives facts judged to be superseded. It can also save user-entered facts without the automatic writer.

## Retrieval and vector index

Memory retrieval combines vector similarity, lexical matches, recency, importance, pin status, and use counts. The service injects a small memory brief plus the current conversation context into a provider request. If embeddings or the Atlas index are unavailable, it can use lexical and recency ranking instead.

To enable Atlas Vector Search:

1. Configure `GEMINI_API_KEY`, `MEMORY_EMBEDDING_MODEL`, and `MEMORY_VECTOR_INDEX` in the backend environment.
2. Create a vector index on `Memory.user_memories` using [`../../backend/memory-vector-index.json`](../../backend/memory-vector-index.json) as the definition.
3. Use the same index name in `MEMORY_VECTOR_INDEX`.

The supplied definition expects 768-dimensional cosine vectors and filter fields `userId` and `status`. Provider embedding/model names and supported dimensions can change; check the provider's current docs when upgrading.

## Storage

The backend creates these collections in the `Memory` database:

- `user_memories`: editable facts, type, confidence, importance, pin/archive state, embedding, and usage metadata.
- `user_conversations`: neutral `user`/`assistant` message history, rolling summary, episode summary, and conversation ID.
- `model_usage`: aggregate request and token counts by user and model, with optional estimated cost.

The legacy `messages` collection is not used by these services and is left intact. Account records remain in the separate `Users` database.

## User controls and API

The Memory page shows active and archived facts, lets users add/edit/pin/delete facts, shows conversation episode summaries, deletes saved conversations, and displays provider-reported tokens. Cost is displayed only when an operator supplies per-model rates. The page also explains that relevant memory is sent to the selected model provider.

The authenticated backend endpoints are documented in [`backend/README.md`](../../backend/README.md). Conversation records and memories are deleted separately: removing browser storage only removes the browser's local list, while the Memory page controls server-side data.

## Limits

Automatic fact extraction can be incorrect, omit relevant facts, or misclassify a contradiction. Users should review what is saved. Deletion prevents future retrieval but cannot recall content already sent to an external provider. Provider retention is governed by that provider's terms. Configure backups and a retention/account-deletion policy for deployed data.

