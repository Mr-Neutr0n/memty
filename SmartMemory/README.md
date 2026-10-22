# NexorAI Smart Auto

This Python package provides a local model router that learns from model outcomes, plus portable JSON memory. It has no required dependencies and makes no provider requests. The optional MongoDB adapter uses the app's existing `Memory.user_memories` collection. The app's current Next.js Auto path also uses task-aware routing in `providers/index.js`.

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
