# Memty Bridge (browser extension)

Use your local Memty vault in Perplexity, ChatGPT, Claude.ai, and Gemini. The extension adds a small **⚡ Memty** pill above the prompt box:

- **⚡ Memty** or **Alt+M** adds your namespace capsule (about 200 tokens at most) to the top of the prompt. It costs no tool calls and no extra turns. The capsule is visible and editable, so you see exactly what is sent.
- **+ Save Facts** extracts facts from the latest answer, or from the text you selected. Extraction runs on your machine. You review the facts, and only the ones you tick are saved.

## Install

1. Start the local bridge: `memty serve --background`
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and choose this `browser-extension` folder.
3. Click the extension icon to open its options.
   - Paste the token printed by `memty serve --show-token`.
   - Pick a namespace, for example `work.project`.
   - Click **Save and test connection**.

Edge and Brave work the same way, through their extensions pages.

## Privacy and security

- The bridge only listens on `127.0.0.1`. It refuses requests from web pages, and every data request needs the pairing token.
- Only the extension's background worker holds the token. The scripts that run inside chat sites never see it.
- Each site counts as a cloud provider (`perplexity`, `openai`, `anthropic`, `google`). The extension derives the provider from the tab's real URL. CONFIDENTIAL values are redacted, and a namespace with a matching SECRET fact is refused.
- Saved facts are stored as `EXTRACTED`, with confidence 0.7. They never overwrite facts you confirmed yourself, and they never bring back slots you deleted.
- To use a local model for extraction, set `MEMTY_OLLAMA_MODEL` (for example `llama3.1`) before running `memty serve`. If Ollama doesn't respond, Memty falls back to heuristics.
- To pin the bridge to your extension's ID, use `memty serve --allow-origin chrome-extension://<id>`.
- To revoke access, run `memty serve --new-token`.

## Known limits

- Chat sites change their page structure often. The prompt-box and answer selectors in `content.js` are best effort. If **Save Facts** can't find the answer, select the answer text first.
- To stop the bridge, run `memty serve --stop`.
