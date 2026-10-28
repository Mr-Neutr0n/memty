"""Optional local MCP server. Agent writes always enter the approval queue."""

from __future__ import annotations

import os
from pathlib import Path

from .factory import default_vault_path, open_ledger
from .ledger import MemoryLedger


def create_server(ledger: MemoryLedger):
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as error:
        raise RuntimeError("MCP support requires Python 3.11+ and: pip install 'nexorai-smart-auto[mcp]'") from error

    server = MCPServer("Nexor Memory Vault", instructions=(
        "Read user-approved memory for context. New or changed facts must be proposed; "
        "never claim a proposal is saved until the user approves it outside this MCP server."
    ))
    trusted_provider = os.getenv("NEXOR_VAULT_PROVIDER", "local")

    @server.tool()
    def read_context(query: str, token_budget: int = 900) -> dict:
        """Read memory allowed for this locally configured provider."""
        compiled = ledger.context(query, provider=trusted_provider, token_budget=token_budget)
        # The placeholder map contains the masked values and must never be exposed to an agent.
        compiled.pop("redactions", None)
        return compiled

    @server.tool()
    def propose_fact(namespace: str, slot_key: str, value: str, confidence: float = 0.8) -> dict:
        """Submit a proposed memory change for user approval; this does not change active memory."""
        proposal_id = ledger.propose(namespace, slot_key, value, confidence=confidence,
                                     extracted_by_model="external-mcp-agent")
        return {"proposal_id": proposal_id, "status": "PENDING_CONFIRMATION"}

    @server.tool()
    def list_my_pending_proposals() -> list[dict]:
        """List changes waiting for the user to approve or reject."""
        return ledger.proposals()

    return server


def main() -> None:
    path = default_vault_path()
    user_id = os.getenv("NEXORAI_MEMORY_USER", os.getenv("NEXOR_VAULT_USER", "local"))
    ledger = open_ledger(user_id, path=path)
    create_server(ledger).run(transport="stdio")


if __name__ == "__main__":
    main()

