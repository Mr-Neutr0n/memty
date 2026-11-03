# Memty

Memty is a user-owned, local memory vault for AI assistants. It stores atomic facts, decisions, and summaries in SQLite and compiles compact context capsules. Its MCP bridge and CLI share a local background daemon, so supported clients can work with the same ledger.

Memty is in alpha and the roadmap is still being developed. Version 0.1 provides the atomic ledger, local daemon, CLI, and MCP bridge. A browser bridge for web assistants, automatic capture, and other roadmap integrations are not yet provided by this release. MCP clients decide when to read resources or call tools; automatic context injection is not guaranteed.

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
| Deterministic context under 600 tokens | Three-section compiler with slot, summary, and semantic sections |
| FTS5 keyword retrieval with SQL fallback | `atomic_facts_fts` and `rolling_summaries_fts`, created when SQLite supports FTS5 |
| SECRET facts in cloud context | The compiler raises `LocalRoutingRequired` when a matching SECRET fact requires local processing |
| CONFIDENTIAL facts can be masked | `<MEMTY_REDACTED_SLOT_N>` placeholders plus `rehydrate()` in the response path |
| Provider allow/block lists | Per-fact `allowed_providers` / `blocked_providers` |

The four functional tables are `atomic_facts`, `logical_constraints`, `rolling_summaries`, and `raw_drilldown`. A small `atomic_fact_audit` table preserves superseded values and is purged on forget.

## Install

```shell
python -m pip install memty
# MCP support is included
```

The vault lives at `~/.memty/ledger.sqlite3` by default. Override it with `MEMTY_VAULT_PATH` or `--db`.

## Quick start: CLI

After installing the package, the following commands create a complete local namespace:

```powershell
memty remember project.api cache_engine "DragonflyDB" --verification USER_CONFIRMED
memty remember project.api rate_limiter "Token Bucket via Lua, 500 req/min" --verification SPEC_LOCKED
memty rule project.api database_queries "writing database queries" "always use async Motor and project only needed fields"
memty summary project.api --set "FastAPI backend with JWT auth and MongoDB Atlas sync."
memty recall "Which cache and rate limiter should I use?" --provider claude --namespace project.api
memty stats
```

Use `memty list`, `memty rules`, `memty history`, `memty forget`, `memty raw-add`, and `memty raw-get` to inspect and manage the vault. The default database is `~/.memty/ledger.sqlite3`; use `--db` or `MEMTY_VAULT_PATH` for another location.

`memty recall` prints a deterministic `<memty_state>` capsule. It never includes archived raw source text. A matching `SECRET` fact exits with status 2 and reports that the request must use a local provider.

## Python API

```python
from memty import open_ledger

vault = open_ledger()  # ~/.memty/ledger.sqlite3, user "local"

vault.record("work.preferences", "editor", "VS Code", verification_state="USER_CONFIRMED")
vault.record("repo.memty", "primary_db", "Postgres 16", verification_state="USER_CONFIRMED")
vault.set_summary("repo.memty", "Memty uses Postgres and a local context compiler.")
vault.set_constraint("repo.memty", "database_queries",
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
repo.memty.primary_db="Postgres 16"
work.preferences.editor="VS Code"
</slots>
<summary ns="repo.memty">Memty uses Postgres and a local context compiler.</summary>
<semantic>
repo.memty.primary_db="Postgres 16"
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
vault.record("repo.memty", "internal_host", "db.internal.example",
             sensitivity="CONFIDENTIAL", verification_state="USER_CONFIRMED")
compiled = vault.context("internal host", provider="claude")
answer = vault.rehydrate(model_output, compiled["redactions"])
# For streamed output, use vault.rehydrate_stream(chunks, compiled["redactions"]).
```

A provider is trusted when it is local (`local`, `ollama`, `local_ollama`, `memty_local`), was passed to `MemtyLedger(..., trusted_providers=[...])`, or is named in that fact's `allowed_providers`.

## Raw drill-down

```python
fact = vault.record("repo.memty", "deployment_host", "db.internal.example",
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
memty summary repo.memty --set "Memty uses Postgres and a local context compiler."
memty forget work.preferences editor --purge-raw
memty stats
memty rule repo.memty database_queries "writing database queries" "always use async Motor and project only needed fields"
memty rules --namespace repo.memty
memty rule-delete repo.memty database_queries
memty migrate ~/.memty/memory.sqlite3
```

`memty recall` exits with status 2 and prints a `local_routing_required` payload when a SECRET fact matches a cloud provider.

## MCP bridge and client setup

Install Memty with `pip install memty`, then run `memty connect`. It detects existing Claude Desktop, Claude Code, Cursor, and Windsurf configuration locations and adds a `memty` server while preserving other settings. Restart the clients after connecting. Invalid JSON is reported without being overwritten. Clients that are not detected are skipped; launch them once and rerun the command.

The clients start `memty mcp` over stdio. The server exposes `memty_sync` (`recall`, `remember`, or `forget`) and the resource template `memty://capsule/{namespace}`. The compiled capsule is limited to 120 estimated tokens. MCP results are treated as an external provider by default, so the ledger's sensitivity rules apply. `MEMTY_PROVIDER` can select another provider identity; choose a local identity only when the receiving model is actually local. Database path and user overrides are `MEMTY_VAULT_PATH` (or `MEMTY_DB`) and `MEMTY_USER`.

The MCP servers and atomic-vault CLI automatically start and share one `memtyd` process for each database path. The daemon serializes their ledger operations and holds a SQLite connection. It uses authenticated loopback connections; its endpoint and secret are stored beside the database, so keep that directory private. The SDK and other applications may still access SQLite directly. WAL and a 5-second busy timeout reduce contention with those external connections, but a lock held longer than the timeout can still cause an error.

```shell
memtyd status
memtyd start
memtyd stop
# For a non-default database, add --db PATH to each command.
# Equivalent: memty daemon status
```

The daemon persists until stopped or the computer exits. It restarts automatically when a client next needs it. Run `memtyd serve` in the foreground to diagnose startup failures.

## Verification

The Week 1 acceptance suite covers the schema, logical constraints, 40-token enforcement, versioning/audit, tombstones, raw isolation, budgets, semantic snippets, summaries, allow/block lists, SECRET routing, and CONFIDENTIAL rehydration:

```shell
python -m pytest tests/test_memty_week1.py -q
python scripts/test_memty_week1.py
```

The performance test builds 200 facts and asserts a warm compiler median below 6 ms on the local machine; the measured median on the development machine is about 3.2 ms (p95 ~4.8 ms) with a 600-token budget and 300 facts. The compiler also enforces a hard `estimate_tokens(text) <= token_budget` check, so larger inputs cannot silently exceed the ceiling.

## Migration from an earlier Memty vault

The SDK can continue reading its previous temporal-vault database format. To copy its latest active facts into the atomic vault:

```shell
memty migrate ~/.memty/memory.sqlite3
```

Only the newest event for each `(namespace, slot)` is considered, so superseded values are not re-imported and deleted slots stay deleted. Facts longer than 40 tokens are skipped and reported rather than truncated.

## Scope of the atomic vault release

The local ledger and compiler use the Python standard library. The distribution includes the MCP dependency. The existing package also contains legacy routing and chat integrations; these are not the focus of the Memty memory-vault roadmap. Browser integration and automatic capture remain future work.
