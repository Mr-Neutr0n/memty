"""Optional MCP server exposing the Memty atomic vault to local agents."""

from __future__ import annotations

import os
from typing import Any

from .compiler import LocalRoutingRequired
from .factory import default_user_id, default_vault_path
from .ledger import MemtyLedger


def create_server(ledger: MemtyLedger):
    instructions = (
        "Memty is a user-owned atomic memory vault. Read only the compiled context returned by "
        "memty_recall. Raw source text is returned only by an explicit memty_drill_down call. "
        "Save or forget facts only when the user explicitly asks. Never claim a fact is saved "
        "unless the tool returned it. SECRET facts force local routing; never retry them on a cloud provider."
    )
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError as error:
            raise RuntimeError(
                "MCP support requires Python 3.11+ and: pip install 'memty[mcp]'"
            ) from error
        server = FastMCP("Memty Atomic Memory", instructions=instructions)
    else:
        server = MCPServer("Memty Atomic Memory", instructions=instructions)
    default_provider = os.getenv("MEMTY_PROVIDER", "local")

    @server.tool()
    def memty_recall(query: str, provider: str = default_provider, token_budget: int = 600,
                     namespace: str | None = None) -> dict:
        """Compile provider-filtered atomic context within a hard token budget."""
        try:
            result = ledger.context(query, provider=provider, token_budget=token_budget,
                                    namespace=namespace)
        except LocalRoutingRequired as error:
            return {"error": "local_routing_required", **error.as_dict()}
        # Masked values must never be exposed to an external agent.
        result.pop("redactions", None)
        return result

    @server.tool()
    def memty_remember(namespace: str, slot: str, value: str, sensitivity: str = "PUBLIC") -> dict:
        """Save one explicit user-requested atomic fact."""
        record = ledger.record(namespace, slot, value, verification_state="USER_CONFIRMED",
                               sensitivity=sensitivity)
        return {"status": "saved", "id": record["id"], "namespace": record["namespace"],
                "slot": record["slot"], "version": record["version"]}

    @server.tool()
    def memty_forget(namespace: str, slot: str, purge_raw: bool = True) -> dict:
        """Tombstone a slot and purge its plaintext history."""
        result = ledger.forget(namespace, slot, purge_raw=purge_raw)
        return {"status": "forgotten" if result else "not_found",
                "namespace": namespace, "slot": slot}

    @server.tool()
    def memty_drill_down(fact_id: str) -> dict:
        """Explicitly fetch the raw source archived behind one atomic fact."""
        result = ledger.drill_down(fact_id=fact_id)
        return result or {"error": "raw_document_not_found", "fact_id": fact_id}

    @server.tool()
    def memty_list(namespace: str | None = None) -> Any:
        """List active atomic facts without raw source text."""
        return ledger.list(namespace=namespace)

    @server.tool()
    def memty_stats() -> dict:
        """Show local vault counters (facts, tombstones, summaries, raw documents)."""
        return ledger.stats()

    return server


def main() -> None:
    ledger = MemtyLedger(default_vault_path(), default_user_id())
    create_server(ledger).run(transport="stdio")


if __name__ == "__main__":
    main()
