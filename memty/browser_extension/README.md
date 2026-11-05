# Memty Bridge (browser extension)

Use your local Memty vault in Perplexity, ChatGPT, Claude.ai, and Gemini. The extension adds a purple **⋮⋮ ⚡ Memty | ＋ Save** pill just above the prompt box. Drag the **⋮⋮** grip to move the pill anywhere on the page. Each site remembers its own position. Double-click the grip to reset it.

- **⚡ Memty** or **Alt+M** adds your saved facts to the top of the prompt as plain `Title: value` lines, newest first. The block uses about 350 tokens at most, so older facts are left out when space runs short. It costs no tool calls and no extra turns, and you can see and edit exactly what is sent:

  ```
  Company: MEMTY
  Category: Portable AI Memory Infrastructure
  Memory store: Memty Vault
  Client: [private]
  ```

- **Select any text** in an answer and a **＋ Save to Memty** bubble appears above it. **＋ Save** on the pill does the same for your selection, or for the latest answer if nothing is selected. Memty proposes atomic facts on your machine. Before you save, you can untick a fact or edit its title or value. Saving counts as your confirmation, so a new value replaces an older one with the same title.
  - Headings, questions, and Memty blocks you pasted earlier are ignored.
  - Bare file paths are combined into one `files` fact.
  - Code is never saved. Each code block becomes one summary fact, for example `JavaScript code in content.js defines injectCapsule, saveFacts`.

## Install (one time)

1. In a terminal, run `memty serve --autostart`. This starts the bridge now and every time you log in, so you never run it again. You can undo it with `memty serve --no-autostart`.
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and choose the folder that `memty extension` prints.

That's all. There's no token to copy and no settings to fill in:

- The extension pairs itself with the bridge the first time you use it.
- It uses the namespace that holds the most facts, or `personal` if your vault is empty. You can pick a different one from the extension icon.
- After you update or reload the extension, open chat tabs get the new version automatically, with no page refresh.

Edge and Brave work the same way, through their extensions pages.

## Your facts, under your control

Click **☰** on the pill, or the extension icon, to open **Your Memty facts**. There you can:

- view every fact in a namespace, newest first
- edit a fact's title or value, or add a new fact
- mark a fact **Private**: chat AIs only see `[private]`, and the value is never shown in the browser
- delete a fact: Memty forgets it completely, including its history, and saving from a chat can't bring it back

## Privacy and security

- The bridge only listens on `127.0.0.1`. It refuses requests from web pages, and every data request needs the pairing token.
- Pairing is trust on first use. The first browser extension that asks the bridge for the token is remembered, and every other extension and every web page is refused. To pair a different browser, run `memty serve --new-token` and restart the bridge, or paste `memty serve --show-token` under **Advanced** in the options.
- Only the extension's background worker holds the token. The scripts that run inside chat sites never see it.
- Each site counts as a cloud provider (`perplexity`, `openai`, `anthropic`, `google`). The extension derives the provider from the tab's real URL. CONFIDENTIAL values are redacted, and a namespace with a matching SECRET fact is refused.
- Saved facts are stored as `EXTRACTED`, with confidence 0.7. They never overwrite facts you confirmed yourself, and they never bring back slots you deleted.
- To use a local model for extraction, set `MEMTY_OLLAMA_MODEL` (for example `llama3.1`) before running `memty serve`. If Ollama doesn't respond, Memty falls back to heuristics.
- To pin the bridge to your extension's ID, use `memty serve --allow-origin chrome-extension://<id>`.
- To revoke access, run `memty serve --new-token`. This also forgets the paired extension.

## Known limits

- Chat sites change their page structure often. The prompt-box and answer selectors in `content.js` are best effort. If **＋ Save** can't find the answer, select the text you want instead.
- To stop the bridge, run `memty serve --stop`.
