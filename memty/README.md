# Memty

Memty is a user-owned atomic memory vault plus a deterministic **sub-600-token context compiler**. It replaces whole-context dumping with canonical slots, capped summaries, and an explicit raw drill-down archive.

Week 1 is the storage and retrieval engine. It is standard-library only, local-first, and makes no model or network calls.

## What Week 1 ships

| Requirement | Implementation |
| --- | --- |
| Atomic facts, one value per slot | `atomic_facts` with `UNIQUE(user_id, namespace, slot)` |
| Logical constraints per namespace | `logical_constraints` with replaceable `rule_id`, condition, and constraint |
| No contradictory memories | Superseding increments `version`, writes the old value to `atomic_fact_audit`, then overwrites the active slot |
| Facts capped at 40 tokens | `record()` rejects anything longer |
| Delete is durable | `forget()` tombstones the slot and purges its plaintext/audit history |
| Automatic extraction cannot resurrect deleted memory | `record(..., verification_state="EXTRACTED")` raises `TombstonedSlot` |
| User can restore a deleted slot | `verification_state="USER_CONFIRMED"` (or `SPEC_LOCKED`) |
| Rolling namespace summaries | `rolling_summaries`, capped at 150 tokens, optional float32 embedding |
| Raw text is never injected | `raw_drilldown` is only returned by an explicit `drill_down()` call |
| Deterministic context under 600 tokens | Three-section compiler: slots ≤250, summary ≤200, semantic ≤150 |
| FTS5 keyword retrieval with SQL fallback | `atomic_facts_fts` and `rolling_summaries_fts`, created when SQLite supports FTS5 |
| SECRET facts cannot leave the device | `LocalRoutingRequired` forces the caller to switch to local `ollama` |
| CONFIDENTIAL facts can be masked | `<MEMTY_REDACTED_SLOT_N>` placeholders plus `rehydrate()` in the response path |
| Provider allow/block lists | Per-fact `allowed_providers` / `blocked_providers` |

The three functional tables are `atomic_facts`, `rolling_summaries`, and `raw_drilldown`. A small `atomic_fact_audit` table preserves superseded values and is purged on forget.

## Install

```shell
pip install memty
# optional MCP server
pip install "memty[mcp]"
```

The vault lives at `~/.memty/ledger.sqlite3` by default. Override it with `MEMTY_VAULT_PATH` or `--db`.

## Quick start

```python
from memty import open_ledger

vault = open_ledger()  # ~/.memty/ledger.sqlite3, user "local"

vault.record("work.preferences", "editor", "VS Code", verification_state="USER_CONFIRMED")
vault.record("repo.nexor", "primary_db", "Postgres 16", verification_state="USER_CONFIRMED")
vault.set_summary("repo.nexor", "Nexor uses Postgres and a local context compiler.")
vault.set_constraint("repo.nexor", "database_queries",
                     "writing database queries",
                     "always use async Motor and project only needed fields")

compiled = vault.context("Which editor and database do I use?", provider="claude", token_budget=600)
print(compiled["text"])
print(compiled["approx_tokens"], compiled["sections"])
```

Typical output:

```xml
<memty_state v="1" provider="claude">
<slots>
repo.nexor.primary_db="Postgres 16"
work.preferences.editor="VS Code"
</slots>
<summary ns="repo.nexor">Nexor uses Postgres and a local context compiler.</summary>
<semantic>
repo.nexor.primary_db="Postgres 16"
</semantic>
</memty_state>
```

The compiler returns `citations`, `redactions`, `approx_tokens`, `eligible_count`, `injected_count`, and per-section counts. The final text is checked against the budget with a conservative token estimator and trimmed if necessary.

## Privacy gate

```python
from memty import LocalRoutingRequired

vault.record("user.vault", "api_key", "...", sensitivity="SECRET",
             verification_state="USER_CONFIRMED")

try:
    vault.context("api key", provider="claude")
except LocalRoutingRequired as exc:
    print(exc.as_dict())  # suggests ollama; no secret value is included

# CONFIDENTIAL facts are masked for untrusted providers.
vault.record("repo.nexor", "internal_host", "db.internal.example",
             sensitivity="CONFIDENTIAL", verification_state="USER_CONFIRMED")
compiled = vault.context("internal host", provider="claude")
answer = vault.rehydrate(model_output, compiled["redactions"])
# For streamed output, use vault.rehydrate_stream(chunks, compiled["redactions"]).
```

A provider is trusted when it is local (`local`, `ollama`, `local_ollama`, `memty_local`, `nexor_local`), was passed to `MemtyLedger(..., trusted_providers=[...])`, or is named in that fact's `allowed_providers`.

## Raw drill-down

```python
fact = vault.record("repo.nexor", "deployment_host", "db.internal.example",
                    verification_state="USER_CONFIRMED",
                    source_raw="full transcript or log excerpt ...")

vault.context("deployment host", provider="local")   # raw text is absent
vault.drill_down(fact_id=fact["id"])                 # explicit fetch only
```

## CLI

```shell
memty --db ~/.memty/ledger.sqlite3 remember work.preferences editor "VS Code"
memty recall "Which editor do I use?" --provider claude --tokens 600
memty list
memty history work.preferences editor
memty summary repo.nexor --set "Nexor uses Postgres and a local context compiler."
memty forget work.preferences editor --purge-raw
memty stats
memty rule repo.nexor database_queries "writing database queries" "always use async Motor and project only needed fields"
memty rules --namespace repo.nexor
memty rule-delete repo.nexor database_queries
memty migrate ~/.nexorai/memory.sqlite3
```

`memty recall` exits with status 2 and prints a `local_routing_required` payload when a SECRET fact matches a cloud provider.

## MCP

```shell
memty-mcp
```

Tools: `memty_recall`, `memty_remember`, `memty_forget`, `memty_drill_down`, `memty_list`, `memty_stats`. The recall tool removes the `redactions` map so an external agent never receives masked values.

## Guarantees and verification

The Week 1 acceptance suite covers the schema, 40-token enforcement, versioning/audit, tombstones, raw isolation, budgets, semantic snippets, summaries, allow/block lists, SECRET routing, and CONFIDENTIAL rehydration:

```shell
python -m pytest tests/test_memty_week1.py -q
```

The performance test builds 200 facts and asserts a warm compiler median below 6 ms on the local machine; the measured median on the development machine is about 3.2 ms (p95 ~4.8 ms) with a 600-token budget and 300 facts. The compiler also enforces a hard `estimate_tokens(text) <= token_budget` check, so larger inputs cannot silently exceed the ceiling.

## Migration from MemoryPort

The old `memoryport`/`nexorai` packages remain installed for backward compatibility. To copy the latest active facts from an old vault:

```shell
memty migrate ~/.nexorai/memory.sqlite3
```

Only the newest event for each `(namespace, slot)` is considered, so superseded values are not re-imported and deleted slots stay deleted. Facts longer than 40 tokens are skipped and reported rather than truncated.

## Not in Week 1

Memory-conditioned routing, the PyPI release pipeline, and the public benchmark report are the next milestones. Week 1 deliberately stops at a tested, dependency-free vault and compiler.
