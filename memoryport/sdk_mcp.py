"""MCP bridge for delegating prompts to the locally configured Memty SDK."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .sdk import Memty, load_client


def create_server(client: Memty):
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as error:
        raise RuntimeError("MCP support requires Python 3.11+ and: pip install 'memty[mcp]'") from error

    server = MCPServer("Memty Model Router", instructions=(
        "This local server can recommend or call a model from the user's configured Memty catalog. "
        "A delegate_prompt call sends its prompt and chat history to the selected provider. "
        "Do not claim this changes the host agent's own model; it delegates a separate request. "
        "The shared Memty vault is available to every configured assistant on this device. "
        "Only save or forget facts when the user explicitly asks; do not import a host transcript silently. "
        "Never include secrets in prompts or ask tools to reveal credentials."
    ))

    @server.tool()
    def recommend_model(prompt: str) -> dict[str, Any]:
        """Recommend a configured model locally without sending the prompt to a provider."""
        route = client.route(prompt)
        return {"model_id": route.model_id, "provider": route.provider, "task_type": route.task_type,
                "reason": route.reason, "alternatives": list(route.alternatives)}

    @server.tool()
    def delegate_prompt(prompt: str, chat_id: str, model_id: str = "auto",
                        system_instruction: str = "") -> dict[str, Any]:
        """Ask a configured model using a unique stable chat_id for this host conversation."""
        answer = client.chat(prompt, chat_id=chat_id, model_id=model_id,
                             system=system_instruction or None)
        return {"text": answer.text, "model_id": answer.model_id, "provider": answer.provider,
                "chat_id": answer.chat_id, "route_reason": answer.route.reason,
                "usage": dict(answer.usage), "latency_ms": answer.latency_ms,
                "estimated_cost_usd": answer.estimated_cost_usd}

    @server.tool()
    def rate_last_response(chat_id: str, outcome: str) -> dict[str, str]:
        """Record explicit user feedback: accepted, within_budget, fallback, correction, regenerated, or neutral."""
        client.feedback(chat_id, outcome=outcome)
        return {"status": "recorded", "chat_id": chat_id, "outcome": outcome}

    @server.tool()
    def search_memory(query: str, model_id: str = "auto") -> dict[str, Any]:
        """Search shared provider-filtered facts from the local Memty vault."""
        result = client.recall(query, model_id=model_id, chat_id="mcp-memory-search")
        result.pop("redactions", None)
        return result

    @server.tool()
    def remember_fact(namespace: str, slot_key: str, value: str) -> dict[str, str]:
        """Save a user-requested fact so it is available to other chats and coding assistants."""
        record = client.remember(namespace, slot_key, value)
        return {"status": "saved", "memory_id": record["id"],
                "namespace": record["namespace"], "slot_key": record["slot_key"]}

    @server.tool()
    def list_configured_models() -> list[dict[str, Any]]:
        """List model names and readiness without exposing API key values."""
        return client.list_models()

    return server


def main() -> None:
    config = Path(os.getenv("MEMTY_CONFIG", os.getenv("NEXORAI_CONFIG", Path.home() / ".memty" / "models.json")))
    load = load_client(config)
    create_server(load).run(transport="stdio")


if __name__ == "__main__":
    main()

