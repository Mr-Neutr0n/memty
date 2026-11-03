"""Compact MCP interface to the shared Memty ledger."""
from __future__ import annotations

import os

from .compiler import LocalRoutingRequired
from .factory import default_user_id, default_vault_path
from .ledger import MemtyLedger


def create_server(ledger: MemtyLedger):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError("MCP support requires: pip install memty") from error
    server = FastMCP("Memty", instructions=(
        "Use memty_sync to recall memory. Save or forget only on explicit user request. "
        "Never claim a change succeeded unless the tool confirms it."
    ))
    # MCP clients may forward results to a remote model; do not treat them as local.
    provider = os.getenv("MEMTY_PROVIDER", "mcp")

    def capsule(namespace: str, query: str = "") -> dict:
        try:
            result = ledger.context(query, provider=provider, namespace=namespace,
                                    token_budget=120, strict_namespace=True)
        except LocalRoutingRequired as error:
            return {"error": "local_routing_required", **error.as_dict()}
        return {"text": result["text"], "approx_tokens": result["approx_tokens"]}

    @server.resource("memty://capsule/{namespace}")
    def memty_capsule(namespace: str) -> str:
        """Read the provider-filtered, 120-token namespace capsule."""
        import json
        return json.dumps(capsule(namespace), ensure_ascii=False)

    @server.tool()
    def memty_sync(namespace: str, action: str = "recall", query: str = "",
                   slot: str = "", value: str = "", sensitivity: str = "PUBLIC") -> dict:
        """Recall a capsule, or explicitly remember or forget a slot for the user."""
        if action == "recall":
            return capsule(namespace, query)
        if action == "remember":
            record = ledger.record(namespace, slot, value, verification_state="USER_CONFIRMED",
                                   sensitivity=sensitivity)
            return {"status": "saved", "namespace": record["namespace"], "slot": record["slot"]}
        if action == "forget":
            result = ledger.forget(namespace, slot, purge_raw=True)
            return {"status": "forgotten" if result else "not_found", "namespace": namespace, "slot": slot}
        raise ValueError("action must be recall, remember, or forget")

    return server


def main() -> None:
    from .daemon import DaemonLedger
    ledger = DaemonLedger(default_vault_path(), default_user_id())
    try:
        create_server(ledger).run(transport="stdio")
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
