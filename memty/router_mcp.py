"""MCP entry point for Memty's smart model router and chat SDK."""

from memoryport.sdk_mcp import create_server, main

__all__ = ["create_server", "main"]

if __name__ == "__main__":
    main()
