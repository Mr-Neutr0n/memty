// Memty Bridge service worker: the only code that talks to the local vault.
// The pairing token stays here and in chrome.storage; web pages never see it.
// Zero setup: the token is fetched from the local bridge (POST /pair, trust on
// first use) and the namespace defaults to the one holding the most facts.

const DEFAULTS = { port: 8765, token: "", namespace: "" };
const FALLBACK_NAMESPACE = "personal";
const NOT_RUNNING = "Memty is not running. Run once in a terminal: memty serve --autostart";

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

const base = (port) => `http://127.0.0.1:${Number(port) || 8765}`;

async function request(url, options, timeoutMs) {
  try {
    // Never leave the chat page waiting on a stuck local server.
    return await fetch(url, { ...options, signal: AbortSignal.timeout(timeoutMs) });
  } catch (error) {
    if (error?.name === "TimeoutError") {
      throw new Error("Memty took too long to answer. Check that memty serve is healthy, then try again.");
    }
    throw new Error(NOT_RUNNING);
  }
}

async function pair() {
  const { port } = await settings();
  const response = await request(`${base(port)}/pair`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  }, 5000);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || !body.token) throw new Error(body.message || "Could not pair with Memty.");
  await chrome.storage.local.set({ token: body.token });
  return body.token;
}

async function call(path, options = {}, timeoutMs = 8000, retried = false) {
  const { port } = await settings();
  const token = (await settings()).token || (await pair());
  const response = await request(`${base(port)}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  }, timeoutMs);
  if (response.status === 401 && !retried) { // token rotated: pair again once
    await chrome.storage.local.remove("token");
    return call(path, options, timeoutMs, true);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || body.error || `HTTP ${response.status}`);
  return body;
}

async function namespace() {
  const saved = (await settings()).namespace;
  if (saved) return saved;
  const { counts = {} } = await call("/namespaces");
  const [best] = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const chosen = best ? best[0] : FALLBACK_NAMESPACE;
  await chrome.storage.local.set({ namespace: chosen });
  return chosen;
}

async function handle(message, sender) {
  const provider = PROVIDERS[new URL(sender.url || sender.tab?.url || "about:blank").hostname] || "web";
  if (message.type === "capsule") {
    const query = new URLSearchParams({ namespace: await namespace(), provider, tokens: "200", format: "text" });
    return call(`/capsule?${query}`);
  }
  if (message.type === "extract") {
    // A local Ollama model may need a while; heuristics answer instantly.
    return call("/extract", { method: "POST", body: JSON.stringify({ text: String(message.text || "") }) }, 25000);
  }
  if (message.type === "save") {
    // The user reviewed and approved these in the card, so they count as confirmed.
    return call("/facts", {
      method: "POST",
      body: JSON.stringify({ namespace: await namespace(), facts: message.facts, source: provider, confirmed: true }),
    });
  }
  if (message.type === "open-facts") {
    await chrome.runtime.openOptionsPage();
    return {};
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

// After install or update, put the fresh script into chat tabs that are already
// open. The stale copy there removes itself, so no page refresh is needed.
chrome.runtime.onInstalled.addListener(async () => {
  const { content_scripts: [script] } = chrome.runtime.getManifest();
  const tabs = await chrome.tabs.query({ url: script.matches });
  await Promise.all(tabs.map((tab) => chrome.scripting
    .executeScript({ target: { tabId: tab.id }, files: script.js })
    .catch(() => {}))); // discarded or restricted tabs: they load it on next visit
  pair().catch(() => {}); // pair early if the bridge is already running
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
