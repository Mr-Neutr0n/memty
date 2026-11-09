# Changelog

All notable changes to the `memty` package. This project follows [Semantic Versioning](https://semver.org/); while it is in 0.x, minor versions may change commands and options.

## Unreleased

- `memty connect` now supports Codex CLI and VS Code through their official MCP installer commands, alongside Claude, Cursor, and Windsurf.
- The stdio MCP server now exposes `memty_drill` for bounded archived-source reads with a local-model-only gate.
- `memty_sync` can save up to 25 explicitly requested slot/value pairs and return the updated capsule in one call.
- Documented that MCP resource registration does not force clients to load memory automatically; clients must call `memty_sync` or read the resource.

## 0.2.0 (2026-11-05)

Brings Memty to web assistants (ChatGPT, Claude.ai, Gemini, Perplexity) and puts you in control of every fact.

### Added
- **Browser extension bundled in the package.** `memty extension` installs the Memty Bridge folder (Chrome, Edge, Brave) at `~/.memty/browser-extension`, and `--open` opens it.
  - **⚡ Memty / Alt+M** adds your facts to the prompt.
  - **Select text → ＋ Save to Memty** proposes atomic facts that you edit before saving.
  - The pill is draggable, and each site remembers its position.
  - New logo icons for light and dark toolbars.
- **Your Memty facts page:** view, search, edit, add, delete, and mark facts private, from the ☰ button or the extension icon.
- **Localhost web bridge (`memty serve`)**, bound to 127.0.0.1 only. Routes: `/capsule`, `/extract`, `/facts`, `/facts/update`, `/facts/delete`, `/namespaces` (with counts), `/pair`, `/health`.
- **Zero-setup pairing.** The extension pairs itself with trust on first use: only one extension origin is accepted, and `--new-token` resets it. It also picks a default namespace on its own. `memty pair` connects another browser or a reinstalled extension.
- **Login autostart.** `memty serve --autostart` and `--no-autostart`: a per-user item on Windows, macOS, and Linux, with no admin rights needed.
- **`memty clip`** copies a capsule to the clipboard for any AI app.
- **Welcome screen.** Running `memty` with no command shows a short introduction and the main commands.
- **Local fact extraction** from chat answers:
  - Uses built-in rules by default, or a local Ollama model when `MEMTY_OLLAMA_MODEL` is set.
  - Skips headings and pasted capsules.
  - Groups file paths into one fact.
  - Summarizes code blocks in one line instead of storing code.

### Changed
- **Plain capsule format.** Capsules for chat assistants and the clipboard are now plain `Title: value` lines. `format=xml` and `--format xml` keep the `<memty_state>` block. MCP and `memty recall` are unchanged.
- **Newest facts first.** Without a query, the newest facts come first, so a fact saved a minute ago is never pushed out by older ones. Web capsules use up to 350 tokens.
- **Reviewed saves are confirmed.** Facts you review and save in the extension are stored as user-confirmed and keep their existing privacy level.
- **`memty connect` is safer.** It never writes another application's settings file. Claude Code and Cursor are connected through their official installers, and Claude Desktop and Windsurf get printed instructions.

### Fixed
- Chats no longer stutter while answers stream: the extension stopped re-measuring the page on every scroll.
- "Extension context invalidated" after an update: stale copies remove themselves, and open tabs get the new version.
- Requests time out with a clear message instead of hanging the chat.
- On Windows, oversized requests sometimes reset the connection before the "413 Request Entity Too Large" reply arrived.
- Snake_case names such as `logical_constraints` are kept intact in extracted facts.

## 0.1.1

- Bug fixes for the atomic vault, CLI, and MCP bridge.

## 0.1.0

- First release: an atomic-fact SQLite vault with versioning, tombstones, and namespace rules; a context compiler under 600 tokens with a privacy gate (SECRET routing and CONFIDENTIAL redaction); a shared `memtyd` daemon; the CLI; and the MCP server (`memty_sync`, `memty://capsule/{namespace}`).
