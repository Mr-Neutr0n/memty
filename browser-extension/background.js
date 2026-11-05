// Memty Bridge service worker: the only code that talks to the local vault.
// The pairing token stays here and in chrome.storage; web pages never see it.

const DEFAULTS = { port: 8765, token: "", namespace: "" };

// The provider is derived from the tab's real URL, never from the page,
// so the vault's per-provider privacy rules cannot be spoofed.
const PROVIDERS = {
  "www.perplexity.ai": "perplexity",
  "perplexity.ai": "perplexity",
  "chatgpt.com": "openai",
  "chat.openai.com": "openai",
  "claude.ai": "anthropic",
  "gemini.google.com": "google",
};

async function settings() {
  return chrome.storage.local.get(DEFAULTS);
}

async function call(path, options = {}) {
  const { port, token } = await settings();
  if (!token) throw new Error("Not paired. Open the Memty Bridge options and paste your token.");
  let response;
  try {
    response = await fetch(`http://127.0.0.1:${Number(port) || 8765}${path}`, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    });
  } catch {
    throw new Error("Memty is not running. Start it with: memty serve --background");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || body.error || `HTTP ${response.status}`);
  return body;
}

async function handle(message, sender) {
  const provider = PROVIDERS[new URL(sender.url || sender.tab?.url || "about:blank").hostname] || "web";
  const { namespace } = await settings();
  if (message.type === "capsule") {
    if (!namespace) throw new Error("Choose a namespace in the Memty Bridge options.");
    const query = new URLSearchParams({ namespace, provider, tokens: "200" });
    return call(`/capsule?${query}`);
  }
  if (message.type === "extract") {
    return call("/extract", { method: "POST", body: JSON.stringify({ text: String(message.text || "") }) });
  }
  if (message.type === "save") {
    if (!namespace) throw new Error("Choose a namespace in the Memty Bridge options.");
    return call("/facts", {
      method: "POST",
      body: JSON.stringify({ namespace, facts: message.facts, source: provider }),
    });
  }
  throw new Error("Unknown request");
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id) return false;
  handle(message, sender).then(
    (result) => reply({ ok: true, result }),
    (error) => reply({ ok: false, error: String(error?.message || error) }),
  );
  return true; // keep the channel open for the async reply
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
